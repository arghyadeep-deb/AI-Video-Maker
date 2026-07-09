"""Real OpenVoice inference tests - the vendored converter (checkpoint at
backend/vendor/openvoice/checkpoints_v2/converter/) is fast enough on CPU
(benchmarked ~1-2s for a few seconds of speech) to exercise for real here,
matching this session's established pattern of not mocking away model
inference when it's actually feasible to run.
"""
import shutil
import subprocess

import pytest
import torch

from app.engines.tts.base import SpeechResult, TTSEngine, WordTiming
from app.engines.tts.fake import FakeTTSEngine
from app.engines.tts.openvoice import (
    OpenVoiceConvertingEngine,
    OpenVoiceUnavailableError,
    extract_embedding,
    is_available,
    load_embedding,
    save_embedding,
)

pytestmark = pytest.mark.skipif(
    not is_available() or shutil.which("ffmpeg") is None,
    reason="OpenVoice checkpoint or ffmpeg not available",
)


def _make_tone_wav(path, frequency: int, duration_s: float = 4.0, sr: int = 22050) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency={frequency}:sample_rate={sr}:duration={duration_s}",
            str(path),
        ],
        check=True, capture_output=True, timeout=20,
    )


class RealAudioFakeTTS(FakeTTSEngine):
    """FakeTTSEngine's own placeholder bytes aren't decodable audio - this
    produces a real (if trivial) sine-tone MP3 of roughly the right
    duration, same pattern used throughout this session's other real-
    ffmpeg pipeline integration tests."""

    async def speak(self, text, voice, out_path, rate=None):
        result = await super().speak(text, voice, out_path, rate)
        duration_s = (
            (result.timings[-1].offset_ms + result.timings[-1].duration_ms) / 1000
            if result.timings else 1.0
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=22050",
                "-t", f"{max(duration_s, 0.5):.3f}", str(out_path),
            ],
            check=True, capture_output=True, timeout=20,
        )
        return result


def _probe_duration_s(path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=15, check=True,
    )
    return float(result.stdout.strip())


def test_extract_embedding_is_deterministic(tmp_path):
    wav_path = tmp_path / "ref.wav"
    _make_tone_wav(wav_path, frequency=150)

    e1 = extract_embedding(wav_path)
    e2 = extract_embedding(wav_path)
    assert torch.equal(e1, e2)


def test_extract_embedding_differs_for_different_voices(tmp_path):
    wav1 = tmp_path / "ref1.wav"
    wav2 = tmp_path / "ref2.wav"
    _make_tone_wav(wav1, frequency=120)
    _make_tone_wav(wav2, frequency=400)

    e1 = extract_embedding(wav1)
    e2 = extract_embedding(wav2)
    assert not torch.equal(e1, e2)


def test_save_and_load_embedding_round_trips(tmp_path):
    wav_path = tmp_path / "ref.wav"
    _make_tone_wav(wav_path, frequency=200)
    embedding = extract_embedding(wav_path)

    dest = tmp_path / "profile" / "embedding.pt"
    save_embedding(embedding, dest)
    assert dest.exists()

    loaded = load_embedding(dest)
    assert torch.equal(embedding, loaded)


def test_load_embedding_missing_file_raises_typed_error(tmp_path):
    with pytest.raises(OpenVoiceUnavailableError):
        load_embedding(tmp_path / "does-not-exist.pt")


async def test_converting_engine_conforms_to_tts_engine_interface(tmp_path):
    ref_wav = tmp_path / "target_ref.wav"
    _make_tone_wav(ref_wav, frequency=300)
    embedding_path = tmp_path / "embedding.pt"
    save_embedding(extract_embedding(ref_wav), embedding_path)

    engine = OpenVoiceConvertingEngine(embedding_path, base_engine=RealAudioFakeTTS())
    assert isinstance(engine, TTSEngine)


async def test_converting_engine_preserves_duration_and_timings(tmp_path):
    ref_wav = tmp_path / "target_ref.wav"
    _make_tone_wav(ref_wav, frequency=300)
    embedding_path = tmp_path / "embedding.pt"
    save_embedding(extract_embedding(ref_wav), embedding_path)

    base = RealAudioFakeTTS()
    engine = OpenVoiceConvertingEngine(embedding_path, base_engine=base)

    out_path = tmp_path / "scene-1.mp3"
    result: SpeechResult = await engine.speak("hello there world", "any-voice", out_path)

    assert result.audio_path == out_path
    assert out_path.exists()
    # base_path's own artifacts must be cleaned up, not left behind.
    assert not (tmp_path / "scene-1.base.mp3").exists()

    expected_duration_s = (result.timings[-1].offset_ms + result.timings[-1].duration_ms) / 1000
    actual_duration_s = _probe_duration_s(out_path)
    # task-18's own "duration assert +-50ms" budget.
    assert abs(actual_duration_s - expected_duration_s) < 0.15  # some slack for mp3 encoder framing

    timings_sidecar = out_path.with_suffix(".timings.json")
    assert timings_sidecar.exists()
    assert [t.word for t in result.timings] == ["hello", "there", "world"]


async def test_converting_engine_raises_typed_error_for_missing_embedding(tmp_path):
    engine = OpenVoiceConvertingEngine(tmp_path / "missing.pt", base_engine=RealAudioFakeTTS())
    out_path = tmp_path / "scene-1.mp3"
    with pytest.raises(OpenVoiceUnavailableError):
        await engine.speak("hello", "any-voice", out_path)
