"""Real Wav2Lip CPU inference — specs/04-tasks/task-11-talking-head.md's own
Tests section calls for this to actually run (not a stub): "Integration
(10s fixture audio + fixture portrait): Wav2Lip CPU render completes;
ffprobe sanity." Needs the vendored repo + downloaded weights
(scripts/setup_models.py) - skipped honestly if either is missing rather
than failing, so the rest of the suite stays green on a machine that
hasn't run setup yet.
"""
import asyncio
import json
import subprocess
import time
from pathlib import Path

import pytest

from app.engines.talking_head.base import TalkingHeadResult
from app.engines.talking_head.wav2lip_local import CHECKPOINT_PATH, Wav2LipLocalEngine

FIXTURE_DIR = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.skipif(
    not CHECKPOINT_PATH.exists(),
    reason="Wav2Lip weights not downloaded - run `python scripts/setup_models.py` first",
)


def _ffprobe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.asyncio
async def test_wav2lip_renders_a_real_talking_head_video(tmp_path):
    engine = Wav2LipLocalEngine()
    output_path = tmp_path / "result.mp4"

    started = time.monotonic()
    result = await engine.render(
        portrait_path=str(FIXTURE_DIR / "test_face.jpg"),
        wav_path=str(FIXTURE_DIR / "test_audio_16k.wav"),
        output_path=str(output_path),
    )
    elapsed_s = time.monotonic() - started
    print(f"\nWav2Lip CPU render took {elapsed_s:.1f}s (dev machine, not the production ARM VM)")

    assert isinstance(result, TalkingHeadResult)
    assert result.engine == "wav2lip"
    assert Path(result.video_path).exists()

    probe = _ffprobe(output_path)
    codec_types = {s["codec_type"] for s in probe["streams"]}
    assert codec_types == {"video", "audio"}

    source_probe = _ffprobe(FIXTURE_DIR / "test_audio_16k.wav")
    source_duration = float(source_probe["format"]["duration"])
    output_duration = float(probe["format"]["duration"])
    assert abs(output_duration - source_duration) < 1.0


@pytest.mark.asyncio
async def test_concurrent_renders_do_not_cross_contaminate(tmp_path):
    """Real bug found live 2026-07-16: every invocation used to share
    VENDOR_DIR as its cwd, and Wav2Lip's own inference.py hardcodes the
    relative path `temp/result.avi` - two invocations overlapping in time
    (e.g. a manual debug run alongside the live job queue, which is
    exactly what happened) raced on that one path. The render that lost
    the race silently produced a video with the *other* run's frame count
    - no error, no crash, just a video ~1.8x longer than its own audio.
    Proves the fix: two renders with genuinely different audio lengths,
    started concurrently, must each end up matching their own audio -
    never swapped, never averaged, never contaminated by the other."""
    short_audio = tmp_path / "short.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(FIXTURE_DIR / "test_audio_16k.wav"), "-t", "3.000", str(short_audio)],
        check=True, capture_output=True, timeout=30,
    )
    short_duration = float(_ffprobe(short_audio)["format"]["duration"])
    long_duration = float(_ffprobe(FIXTURE_DIR / "test_audio_16k.wav")["format"]["duration"])
    assert short_duration < long_duration - 1.0  # the two renders must be genuinely distinguishable

    engine_a = Wav2LipLocalEngine()
    engine_b = Wav2LipLocalEngine()
    output_a = tmp_path / "result_a.mp4"
    output_b = tmp_path / "result_b.mp4"

    result_a, result_b = await asyncio.gather(
        engine_a.render(
            portrait_path=str(FIXTURE_DIR / "test_face.jpg"),
            wav_path=str(short_audio),
            output_path=str(output_a),
        ),
        engine_b.render(
            portrait_path=str(FIXTURE_DIR / "test_face.jpg"),
            wav_path=str(FIXTURE_DIR / "test_audio_16k.wav"),
            output_path=str(output_b),
        ),
    )

    duration_a = float(_ffprobe(Path(result_a.video_path))["format"]["duration"])
    duration_b = float(_ffprobe(Path(result_b.video_path))["format"]["duration"])
    assert abs(duration_a - short_duration) < 1.0
    assert abs(duration_b - long_duration) < 1.0
