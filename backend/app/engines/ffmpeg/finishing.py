"""FFmpeg finishing for Mode A — specs/04-tasks/task-12-mode-a-assembly.md,
specs/03-design/04-mode-a-pipeline.md's assemble stage: "scale/pad to chosen
format (blurred pad if aspect mismatch), burn ASS subtitles if toggle ON,
loudnorm, final H.264 encode".
"""
from pathlib import Path

Orientation = str  # "portrait" | "landscape" | "square"


def _orientation(width: int, height: int) -> Orientation:
    if width == height:
        return "square"
    return "portrait" if height > width else "landscape"


def needs_padding(src_width: int, src_height: int, target_width: int, target_height: int) -> bool:
    """A source needs blurred padding (rather than a plain cover-crop) only
    when its orientation is the OPPOSITE of the target's - e.g. a portrait
    source into a 16:9 target, or a landscape source into a 9:16 target.

    A square source never needs padding either way - it covers any target
    cleanly via a center crop. This matters here because this product's
    avatar portraits are always 1024x1024 (specs/03-design/04-mode-a-pipeline.md's
    fixed prompt suffix), so Mode A's actual case is always the "native,
    no padding" branch in practice - the padding branch exists for
    robustness against any source dimensions, not because avatars need it.
    """
    src_o = _orientation(src_width, src_height)
    target_o = _orientation(target_width, target_height)
    if src_o == "square" or target_o == "square":
        return False
    return src_o != target_o


def build_scale_pad_filter(
    src_width: int,
    src_height: int,
    target_width: int,
    target_height: int,
    input_label: str = "0:v",
    output_label: str = "scaled",
) -> str:
    if needs_padding(src_width, src_height, target_width, target_height):
        return (
            f"[{input_label}]split=2[fg][bgsrc];"
            f"[bgsrc]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height},gblur=sigma=20[bg];"
            f"[fg]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease[fgscaled];"
            f"[bg][fgscaled]overlay=(W-w)/2:(H-h)/2[{output_label}]"
        )
    return (
        f"[{input_label}]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
        f"crop={target_width}:{target_height}[{output_label}]"
    )


def escaped_ffmpeg_path(path: Path) -> str:
    """ffmpeg's filtergraph parser splits on ':' - a bare Windows drive
    letter colon (C:) breaks it, so escape it. Also used for the ass=
    filename itself: it must be an absolute path since the ffmpeg
    subprocess's cwd is not the project directory. Same fix as
    app/pipelines/mode_b.py's own `_escaped_ffmpeg_path` (task-09) -
    duplicated rather than imported to keep this module's public surface
    self-contained; both are one-line functions unlikely to drift.
    """
    posix = str(path).replace("\\", "/")
    if len(posix) > 1 and posix[1] == ":":
        posix = posix[0] + "\\:" + posix[2:]
    return posix


def build_subtitle_filter(
    ass_path: Path, fonts_dir: Path, input_label: str, output_label: str = "vsub"
) -> str:
    return (
        f"[{input_label}]ass='{escaped_ffmpeg_path(ass_path)}':"
        f"fontsdir='{escaped_ffmpeg_path(fonts_dir)}'[{output_label}]"
    )
