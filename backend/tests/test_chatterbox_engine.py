"""ChatterboxRemoteEngine + PersonalVoiceChain — task-23's voice
expressiveness upgrade. Fake gradio clients via client_factory (the
sadtalker/voxcpm/ltx DI pattern); forced alignment monkeypatched so no
model download happens here. Torch-free by design: the chain logic lives
on base.py's PersonalVoiceUnavailableError, not on openvoice imports.
"""
import asyncio
from pathlib import Path

import pytest

from app.engines.tts.base import PersonalVoiceUnavailableError, SpeechResult, TTSEngine, WordTiming
from app.engines.tts.chatterbox_remote import (
    ChatterboxRemoteEngine,
    ChatterboxUnavailableError,
    chunk_text,
    language_id_for_voice,
)


class _FakeClient:
    def __init__(self, audio_factory, exc: Exception | None = None):
        self._audio_factory = audio_factory
        self._exc = exc
        self.calls: list[dict] = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return str(self._audio_factory(len(self.calls)))


def _fake_timings(text: str) -> list[WordTiming]:
    return [
        WordTiming(word=w, offset_ms=i * 500, duration_ms=400)
        for i, w in enumerate(text.split())
    ]


@pytest.fixture
def patch_alignment(monkeypatch):
    import app.services.forced_alignment as fa

    monkeypatch.setattr(fa, "forced_align", lambda audio_path, text: _fake_timings(text))


def _make_ref(tmp_path: Path) -> Path:
    ref = tmp_path / "enrollment.wav"
    ref.write_bytes(b"RIFFfake")
    return ref


# --- chunking -----------------------------------------------------------


def test_short_text_is_a_single_chunk():
    assert chunk_text("नमस्ते दोस्तों, आज का दिन शानदार है।") == [
        "नमस्ते दोस्तों, आज का दिन शानदार है।"
    ]


def test_long_text_splits_under_300_chars_at_word_boundaries():
    sentence = "अपना रूटीन बनाएं और शेड्यूल पर फोकस रखें। "
    text = (sentence * 12).strip()  # ~500+ chars
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    assert all(len(c) <= 300 for c in chunks)
    # No word is ever cut: rejoining chunks with spaces reproduces the text.
    assert " ".join(chunks).split() == text.split()


def test_language_id_derivation():
    assert language_id_for_voice("hi-IN-SwaraNeural") == "hi"
    assert language_id_for_voice("en-US-AriaNeural") == "en"


# --- engine -------------------------------------------------------------


def test_single_chunk_speak_writes_audio_and_sidecar(tmp_path, patch_alignment):
    audio_src = tmp_path / "space_result.wav"
    audio_src.write_bytes(b"expressive audio bytes")
    fake = _FakeClient(lambda n: audio_src)
    engine = ChatterboxRemoteEngine(
        reference_wav_path=_make_ref(tmp_path), client_factory=lambda: fake
    )

    out = tmp_path / "narration.wav"
    result = asyncio.run(engine.speak("नमस्ते दोस्तों।", "hi-IN-SwaraNeural", out))

    assert out.read_bytes() == b"expressive audio bytes"
    assert out.with_suffix(".timings.json").exists()
    assert [t.word for t in result.timings] == ["नमस्ते", "दोस्तों।"]
    call = fake.calls[0]
    assert call["api_name"] == "/generate_tts_audio"
    assert call["language_id"] == "hi"
    assert call["text_input"] == "नमस्ते दोस्तों।"


def test_client_cached_across_calls(tmp_path, patch_alignment):
    audio_src = tmp_path / "r.wav"
    audio_src.write_bytes(b"x")
    fake = _FakeClient(lambda n: audio_src)
    factory_calls = {"n": 0}

    def factory():
        factory_calls["n"] += 1
        return fake

    engine = ChatterboxRemoteEngine(reference_wav_path=_make_ref(tmp_path), client_factory=factory)
    for i in range(2):
        asyncio.run(engine.speak("हैलो जी।", "hi-IN-SwaraNeural", tmp_path / f"o{i}.wav"))
    assert factory_calls["n"] == 1


def test_space_failure_becomes_chatterbox_unavailable(tmp_path):
    fake = _FakeClient(lambda n: "unused", exc=RuntimeError("ZeroGPU quota exceeded"))
    engine = ChatterboxRemoteEngine(reference_wav_path=_make_ref(tmp_path), client_factory=lambda: fake)
    with pytest.raises(ChatterboxUnavailableError, match="quota"):
        asyncio.run(engine.speak("टेक्स्ट।", "hi-IN-SwaraNeural", tmp_path / "o.wav"))


def test_missing_enrollment_sample_fails_the_tier_not_the_render(tmp_path):
    engine = ChatterboxRemoteEngine(
        reference_wav_path=tmp_path / "deleted.wav", client_factory=lambda: _FakeClient(lambda n: "x")
    )
    with pytest.raises(ChatterboxUnavailableError, match="enrollment sample"):
        asyncio.run(engine.speak("टेक्स्ट।", "hi-IN-SwaraNeural", tmp_path / "o.wav"))
    # It's a PersonalVoiceUnavailableError, so the chain degrades honestly.
    assert issubclass(ChatterboxUnavailableError, PersonalVoiceUnavailableError)


def test_alignment_failure_degrades_the_tier(tmp_path, monkeypatch):
    import app.services.forced_alignment as fa

    def boom(audio_path, text):
        raise fa.ForcedAlignmentError("no confident words")

    monkeypatch.setattr(fa, "forced_align", boom)
    audio_src = tmp_path / "r.wav"
    audio_src.write_bytes(b"x")
    engine = ChatterboxRemoteEngine(
        reference_wav_path=_make_ref(tmp_path), client_factory=lambda: _FakeClient(lambda n: audio_src)
    )
    with pytest.raises(ChatterboxUnavailableError, match="forced alignment"):
        asyncio.run(engine.speak("टेक्स्ट।", "hi-IN-SwaraNeural", tmp_path / "o.wav"))


# --- chain --------------------------------------------------------------


class _TierStub(TTSEngine):
    def __init__(self, fail: bool, name: str):
        self.fail = fail
        self.name = name
        self.called = 0

    async def speak(self, text, voice, out_path, rate=None):
        self.called += 1
        if self.fail:
            raise ChatterboxUnavailableError(f"{self.name} down")
        Path(out_path).write_bytes(b"ok")
        return SpeechResult(audio_path=Path(out_path), timings=_fake_timings(text))


def test_chain_falls_through_tiers_in_order(tmp_path):
    from app.pipelines.common import PersonalVoiceChain

    first, second = _TierStub(fail=True, name="chatterbox"), _TierStub(fail=False, name="openvoice")
    chain = PersonalVoiceChain([first, second])
    result = asyncio.run(chain.speak("हैलो।", "hi-IN-SwaraNeural", tmp_path / "o.wav"))
    assert (first.called, second.called) == (1, 1)
    assert result.audio_path.read_bytes() == b"ok"


def test_chain_raises_last_error_when_all_tiers_fail(tmp_path):
    from app.pipelines.common import PersonalVoiceChain

    chain = PersonalVoiceChain([_TierStub(True, "a"), _TierStub(True, "b")])
    with pytest.raises(PersonalVoiceUnavailableError, match="b down"):
        asyncio.run(chain.speak("हैलो।", "hi-IN-SwaraNeural", tmp_path / "o.wav"))


def test_fallback_narration_engine_stocks_out_with_notice(tmp_path):
    from app.pipelines.common import FallbackNarrationEngine

    stock = _TierStub(fail=False, name="stock")
    engine = FallbackNarrationEngine(primary=_TierStub(True, "personal"), stock=stock)
    asyncio.run(engine.speak("हैलो।", "hi-IN-SwaraNeural", tmp_path / "o.wav"))
    assert engine.used_stock_fallback is True
    assert "personal down" in engine.fallback_reason
    assert stock.called == 1
