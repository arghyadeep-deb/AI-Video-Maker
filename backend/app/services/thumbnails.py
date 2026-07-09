"""Project thumbnails — specs/04-tasks/task-13-library-delivery.md.

Mode B: a frame grabbed at 10% into the finished render. Mode A: the
avatar's own approved portrait (no ffmpeg needed - it already represents
the video, and grabbing it "pre-render" per the task's own Implementation
notes means before/without needing the animated output at all).
"""
import shutil
import subprocess
from pathlib import Path


class ThumbnailError(Exception):
    pass


def write_video_frame_thumbnail(video_path: Path, thumbnail_path: Path, duration_s: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ThumbnailError("ffmpeg not found on PATH")
    seek_s = max(0.1, duration_s * 0.1)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg, "-y", "-ss", f"{seek_s:.2f}", "-i", str(video_path),
            "-frames:v", "1", "-q:v", "3", str(thumbnail_path),
        ],
        check=True, capture_output=True, timeout=15,
    )


def write_portrait_thumbnail(portrait_path: Path, thumbnail_path: Path) -> None:
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.write_bytes(Path(portrait_path).read_bytes())
