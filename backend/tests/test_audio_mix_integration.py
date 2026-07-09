"""Real ffmpeg integration test for the music-ducking filter —
specs/04-tasks/task-16-music-subtitle-styles.md's own Tests section:
"render with music -> ffprobe two source audio inputs mixed to one
stream; narration intelligible (loudness ratio asserted)".
"""
import json
import re
import shutil
import subprocess

import pytest

from app.engines.ffmpeg.audio_mix import build_music_duck_filter

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")

DURATION_S = 6.0


def _make_tone(path, frequency: int, volume: float, duration_s: float = DURATION_S) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency={frequency}:sample_rate=44100:duration={duration_s}",
            "-af", f"volume={volume}", str(path),
        ],
        check=True, capture_output=True, timeout=15,
    )


def _mean_volume_db(path) -> float:
    result = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=15,
    )
    match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", result.stderr)
    assert match, f"volumedetect output missing mean_volume:\n{result.stderr}"
    return float(match.group(1))


def _ffprobe_streams(path) -> list[dict]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=15, check=True,
    )
    return json.loads(result.stdout)["streams"]


def test_ducked_mix_stays_close_to_narration_not_the_loud_music(tmp_path):
    narration_path = tmp_path / "narration.wav"
    music_path = tmp_path / "music.wav"
    output_path = tmp_path / "mixed.wav"

    # A continuous "narration" tone (simulating constant speech, worst case
    # for ducking - real speech has gaps the compressor releases into) and
    # a MUCH louder, different-frequency "music" tone.
    _make_tone(narration_path, frequency=440, volume=0.3)
    _make_tone(music_path, frequency=220, volume=1.0)

    narration_alone_db = _mean_volume_db(narration_path)
    music_alone_db = _mean_volume_db(music_path)
    # Sanity check the fixture itself: music really is much louder than
    # narration before any ducking, or this test proves nothing.
    assert music_alone_db > narration_alone_db + 8

    filter_complex = build_music_duck_filter("1:a", "0:a", duration_s=DURATION_S, output_label="aout")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(narration_path),
            "-i", str(music_path),
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            str(output_path),
        ],
        check=True, capture_output=True, timeout=15,
    )

    streams = _ffprobe_streams(output_path)
    assert len(streams) == 1
    assert streams[0]["codec_type"] == "audio"

    mixed_db = _mean_volume_db(output_path)
    # Ducking + baseline attenuation should land the mix much closer to the
    # narration's own level than to the (much louder) raw music level -
    # this is the actual "narration stays intelligible" property, not just
    # "some ducking happened".
    distance_to_narration = abs(mixed_db - narration_alone_db)
    distance_to_music = abs(mixed_db - music_alone_db)
    assert distance_to_narration < distance_to_music
