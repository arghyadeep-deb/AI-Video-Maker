"""Typed FFmpeg command builder — specs/02-research/06-ffmpeg-assembly.md.

A thin, testable wrapper: build the arg list as data, assert on it in unit
tests, only actually invoke a subprocess in the pipeline / live tests.
"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FFmpegCommand:
    # Each entry is the full arg sequence for one input, e.g.
    # ["-loop", "1", "-t", "3.500", "-i", "img.jpg"] or ["-i", "audio.mp3"] -
    # per-input flags like -loop/-t must precede that input's own -i.
    inputs: list[list[str]] = field(default_factory=list)
    filter_complex: str | None = None
    maps: list[str] = field(default_factory=list)
    output_args: list[str] = field(default_factory=list)
    output_path: str = ""

    def to_args(self, ffmpeg_bin: str = "ffmpeg") -> list[str]:
        args = [ffmpeg_bin, "-y"]
        for input_args in self.inputs:
            args += input_args
        if self.filter_complex:
            args += ["-filter_complex", self.filter_complex]
        args += self.maps
        args += self.output_args
        args += [self.output_path]
        return args


def input_image_still(path: Path) -> list[str]:
    """Input args for a still image, fed as a single frame - `zoompan`
    expects exactly one input frame and expands it into `d` output frames
    itself (see kenburns.py's `_zoompan_filter`). Looping the input first
    (`-loop 1 -t duration`, this function's previous behavior) instead
    feeds zoompan one input frame per demuxer tick (image2's default is
    25 fps), and it multiplies its own `d` output frames by *each* of
    those - a real bug found live 2026-07-16: a ~55 s video rendered as
    ~91,000 frames (>3000 s) on this box's ffmpeg 6.1.1/aarch64 build.
    `-shortest` on the final mux does not reliably mask this for a
    filter_complex-generated stream (confirmed live), so the fix has to
    be at the source, not a downstream duration cap."""
    return ["-i", str(path)]


def input_audio(path: Path) -> list[str]:
    return ["-i", str(path)]


def input_video(path: Path) -> list[str]:
    """A generated-footage motion clip (task-20a). No -loop/-t: the
    filtergraph's trim+tpad owns its duration."""
    return ["-i", str(path)]


def input_music_looped(path: Path, duration_s: float) -> list[str]:
    """Input args for a music track looped (if shorter than the video) and
    trimmed to exactly `duration_s` - specs/04-tasks/task-16-music-subtitle-styles.md.
    `-t` is an input option here (matching input_image_looped's own
    ordering) - it must precede `-i` to limit how much of *this* input is
    read, not the output's overall duration. `-stream_loop -1` is a no-op
    cost-wise for tracks already longer than duration_s (ffmpeg simply
    never needs the second loop iteration)."""
    return ["-stream_loop", "-1", "-t", f"{duration_s:.3f}", "-i", str(path)]
