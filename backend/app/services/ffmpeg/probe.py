"""ffmpeg capability probes, shared by the task-01 health check and
task-06's subtitle burn pipeline (which needs libass/HarfBuzz specifically).
"""
import shutil
import subprocess


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffmpeg_status() -> dict:
    path = ffmpeg_path()
    if not path:
        return {"present": False, "version": None}
    try:
        result = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=5, check=False
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else None
        return {"present": True, "version": first_line}
    except (OSError, subprocess.SubprocessError):
        return {"present": True, "version": None}


def probe_duration_s(path) -> float | None:
    """ffprobe-based duration, in seconds - used to validate an admin-imported
    render (task-11's import-render escape hatch) against the audio it was
    supposed to match."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return float(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def subtitle_filters_available() -> bool:
    """Does this ffmpeg build support the `ass` filter (needs libass +
    HarfBuzz for correct Devanagari conjunct/matra shaping)."""
    path = ffmpeg_path()
    if not path:
        return False
    try:
        result = subprocess.run(
            [path, "-filters"], capture_output=True, text=True, timeout=5, check=False
        )
        return " ass " in f" {result.stdout.lower()} "
    except (OSError, subprocess.SubprocessError):
        return False
