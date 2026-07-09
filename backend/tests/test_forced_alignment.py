"""Real forced-alignment test against an actual edge-tts-synthesized clip
(this dev environment has network access to the free edge-tts service,
confirmed by prior tasks' own live smoke tests) - proves faster-whisper's
"tiny" model produces genuinely usable, monotonic word timings for real
speech, not just a mock.
"""
import pytest

from app.services.forced_alignment import ForcedAlignmentError, forced_align


async def test_forced_align_produces_monotonic_timings_for_real_speech(tmp_path):
    from app.engines.tts.edge import EdgeTTSEngine

    text = "Hello there, this is a short test sentence."
    audio_path = tmp_path / "speech.mp3"
    try:
        await EdgeTTSEngine().speak(text, "en-US-AriaNeural", audio_path)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"edge-tts unreachable in this environment: {exc}")

    timings = forced_align(audio_path, text)
    assert len(timings) > 0
    offsets = [t.offset_ms for t in timings]
    assert offsets == sorted(offsets)
    assert all(t.duration_ms >= 0 for t in timings)


def test_forced_align_raises_typed_error_for_silence(tmp_path):
    import subprocess

    silent_path = tmp_path / "silence.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=sample_rate=16000", "-t", "2", str(silent_path)],
        check=True, capture_output=True, timeout=15,
    )
    with pytest.raises(ForcedAlignmentError):
        forced_align(silent_path, "some reference text")
