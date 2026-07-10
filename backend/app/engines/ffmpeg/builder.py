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


def input_image_looped(path: Path, duration_s: float) -> list[str]:
    """Input args for a still image looped for `duration_s` seconds."""
    return ["-loop", "1", "-t", f"{duration_s:.3f}", "-i", str(path)]


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
