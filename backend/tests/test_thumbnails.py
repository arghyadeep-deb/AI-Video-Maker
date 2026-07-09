import shutil
import subprocess

import pytest

from app.services.thumbnails import write_portrait_thumbnail, write_video_frame_thumbnail

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def _make_test_video(path, duration_s: float = 3.0) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=red:s=320x240:d={duration_s}", str(path)],
        check=True, capture_output=True, timeout=15,
    )


def test_write_video_frame_thumbnail_produces_a_real_image(tmp_path):
    video_path = tmp_path / "video.mp4"
    _make_test_video(video_path, duration_s=3.0)
    thumbnail_path = tmp_path / "thumb.jpg"

    write_video_frame_thumbnail(video_path, thumbnail_path, duration_s=3.0)

    assert thumbnail_path.exists()
    assert thumbnail_path.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(thumbnail_path)],
        capture_output=True, text=True, timeout=10, check=True,
    )
    assert "video" in probe.stdout


def test_write_video_frame_thumbnail_creates_parent_dirs(tmp_path):
    video_path = tmp_path / "video.mp4"
    _make_test_video(video_path)
    thumbnail_path = tmp_path / "nested" / "dir" / "thumb.jpg"

    write_video_frame_thumbnail(video_path, thumbnail_path, duration_s=3.0)
    assert thumbnail_path.exists()


def test_write_portrait_thumbnail_copies_bytes(tmp_path):
    portrait_path = tmp_path / "portrait.png"
    portrait_path.write_bytes(b"fake-portrait-bytes")
    thumbnail_path = tmp_path / "sub" / "thumb.jpg"

    write_portrait_thumbnail(portrait_path, thumbnail_path)

    assert thumbnail_path.read_bytes() == b"fake-portrait-bytes"
