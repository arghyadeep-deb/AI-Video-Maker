import pytest

from app.engines.tts.base import WordTiming
from app.engines.tts.edge import EdgeTTSEngine, EdgeTTSUnavailableError
from app.engines.tts.fake import FakeTTSEngine


def test_word_timing_is_a_plain_shape():
    t = WordTiming(word="नमस्ते", offset_ms=100, duration_ms=250)
    assert t.word == "नमस्ते"
    assert t.offset_ms == 100
    assert t.duration_ms == 250


async def test_fake_tts_produces_audio_and_monotonic_timings(tmp_path):
    engine = FakeTTSEngine()
    out_path = tmp_path / "scene-1.mp3"
    result = await engine.speak("hello world foo", "any-voice", out_path)

    assert result.audio_path.exists()
    assert result.audio_path.stat().st_size > 0
    assert [t.word for t in result.timings] == ["hello", "world", "foo"]

    offsets = [t.offset_ms for t in result.timings]
    assert offsets == sorted(offsets)

    timings_sidecar = out_path.with_suffix(".timings.json")
    assert timings_sidecar.exists()
    assert timings_sidecar.name == "scene-1.timings.json"


async def test_fake_tts_conforms_to_tts_engine_interface():
    """Proves the engine-swap point: FakeTTSEngine can stand in anywhere a
    TTSEngine is expected (task-05 acceptance criteria)."""
    from app.engines.tts.base import TTSEngine

    assert isinstance(FakeTTSEngine(), TTSEngine)
    assert isinstance(EdgeTTSEngine(), TTSEngine)


@pytest.mark.parametrize(
    ("text", "voice", "min_words"),
    [
        ("नमस्ते, यह एक परीक्षण है।", "hi-IN-SwaraNeural", 4),
        ("Hello, this is a test.", "en-IN-NeerjaNeural", 4),
    ],
)
async def test_edge_tts_live_synthesis(tmp_path, text, voice, min_words):
    """Live, cheap integration check (task-05's own Tests section calls for
    this). Skips gracefully if this environment can't reach the
    unofficial edge-tts service — that's an honest degradation the engine
    itself already maps to EdgeTTSUnavailableError.
    """
    engine = EdgeTTSEngine()
    out_path = tmp_path / "out.mp3"
    try:
        result = await engine.speak(text, voice, out_path)
    except EdgeTTSUnavailableError:
        pytest.skip("edge-tts service unreachable from this environment")

    assert result.audio_path.stat().st_size > 0
    assert len(result.timings) >= min_words

    offsets = [t.offset_ms for t in result.timings]
    assert offsets == sorted(offsets), "word offsets must be monotonically increasing"
    assert all(t.duration_ms > 0 for t in result.timings)

    sidecar = out_path.with_suffix(".timings.json")
    assert sidecar.exists()
