"""Ken Burns + crossfade recipe — specs/03-design/05-mode-b-pipeline.md.

Timing model (the backbone; "no drift possible because there is no second
clock"): each scene's rendered clip is its own audio duration *plus* half a
crossfade for each adjacent transition it participates in. Chaining N such
clips with (N-1) xfade transitions of `XFADE_S` each collapses the padding
back out exactly, so the final visual timeline length equals the sum of the
per-scene audio durations - matching the concatenated audio track exactly.
"""
from dataclasses import dataclass

XFADE_S = 0.5
FPS = 30
MAX_ZOOM = 1.5


@dataclass(frozen=True)
class SceneClip:
    index: int  # 0-based position in the render order
    image_path: str
    duration_s: float  # this scene's own audio duration
    # Generated-footage level (task-20a): a real AI-generated motion clip
    # for this scene. When set, the scene renders from the clip (held on
    # its last frame past its ~5 s: "scene duration beyond the clip's ~5 s
    # is bridged by a slow hold... so audio always rules the timeline" -
    # specs/01-requirements/05-mode-b-image-video.md) instead of Ken Burns.
    video_path: str | None = None


def clip_render_duration(
    scene_index: int, n_scenes: int, duration_s: float, xfade_s: float = XFADE_S
) -> float:
    """L_i: how long this scene's Ken Burns clip must actually render for,
    padded by half a crossfade on each side it borders. A single-scene
    video has no transitions, so no padding.
    """
    if n_scenes <= 1:
        return duration_s
    if scene_index in (0, n_scenes - 1):
        return duration_s + xfade_s / 2
    return duration_s + xfade_s


def total_timeline_duration_s(scene_durations: list[float], xfade_s: float = XFADE_S) -> float:
    """The final assembled video's length - must equal sum(scene_durations)
    regardless of scene count, by construction of clip_render_duration.
    """
    return sum(scene_durations)


OVERSAMPLE_FACTOR = 2  # multiple of the larger target dimension


def _zoompan_filter(render_duration_s: float, width: int, height: int, zoom_in: bool) -> str:
    frames = max(1, round(render_duration_s * FPS))
    zoom_range = MAX_ZOOM - 1.0
    # Closed-form z(on) rather than zoompan's stateful `zoom+=` accumulation
    # pattern - deterministic, and avoids relying on internal filter state
    # semantics that vary subtly across ffmpeg versions.
    if zoom_in:
        zoom_expr = f"1+{zoom_range}*on/{frames}"
    else:
        zoom_expr = f"{MAX_ZOOM}-{zoom_range}*on/{frames}"
    # Oversample before zoompan (per common ffmpeg Ken Burns recipe) so the
    # pan doesn't visibly step; scale back down to the target frame size.
    # Anchored to whichever target dimension is larger (not a flat 8000px,
    # which was ~113 MP for a 1080x1920 target and made CPU renders
    # unacceptably slow - see task-09 Completion notes).
    if height >= width:
        scale_filter = f"scale=-2:{height * OVERSAMPLE_FACTOR}"
    else:
        scale_filter = f"scale={width * OVERSAMPLE_FACTOR}:-2"
    return (
        f"{scale_filter},"
        f"zoompan=z='{zoom_expr}':d={frames}:s={width}x{height}:fps={FPS}"
    )


def _footage_filter(render_duration_s: float, width: int, height: int) -> str:
    """Generated-footage scene: normalize the AI clip to the target frame
    (cover-fit crop), pin the frame rate, hold the last frame indefinitely
    (`tpad` clone; tpad has no whole_dur - that's apad's option), then trim
    to the exact render duration. Works for clips shorter OR longer than
    the scene's audio without probing the clip, and the exact duration
    keeps the xfade offset math identical to the Ken Burns branch."""
    return (
        f"fps={FPS},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"tpad=stop_mode=clone:stop=-1,"
        f"trim=duration={render_duration_s:.3f},setpts=PTS-STARTPTS"
    )


def build_kenburns_filter_complex(
    clips: list[SceneClip], width: int, height: int, xfade_s: float = XFADE_S
) -> tuple[str, str]:
    """Returns (filter_complex_string, output_video_label). Assumes each
    clip's image (or motion clip, for generated footage) is input index
    `clip.index` (0-based, in render order).
    """
    n = len(clips)
    if n == 0:
        raise ValueError("at least one scene clip is required")

    per_clip_filters = []
    labels = []
    for clip in clips:
        render_duration = clip_render_duration(clip.index, n, clip.duration_s, xfade_s)
        if clip.video_path is not None:
            vf = _footage_filter(render_duration, width, height)
        else:
            zoom_in = clip.index % 2 == 0
            vf = _zoompan_filter(render_duration, width, height, zoom_in)
        label = f"v{clip.index}"
        per_clip_filters.append(f"[{clip.index}:v]{vf},format=yuv420p,setsar=1[{label}]")
        labels.append(label)

    if n == 1:
        filter_complex = ";".join(per_clip_filters) + f";[{labels[0]}]null[vout]"
        return filter_complex, "vout"

    xfade_filters = []
    cumulative = clip_render_duration(0, n, clips[0].duration_s, xfade_s)
    prev_label = labels[0]
    for i in range(1, n):
        render_duration = clip_render_duration(i, n, clips[i].duration_s, xfade_s)
        offset = cumulative - xfade_s
        out_label = f"x{i}" if i < n - 1 else "vout"
        xfade_filters.append(
            f"[{prev_label}][{labels[i]}]xfade=transition=fade:duration={xfade_s}:"
            f"offset={offset:.3f}[{out_label}]"
        )
        cumulative = cumulative + render_duration - xfade_s
        prev_label = out_label

    filter_complex = ";".join(per_clip_filters + xfade_filters)
    return filter_complex, "vout"


def build_audio_concat_filter(n_scenes: int, audio_input_start_index: int) -> tuple[str, str]:
    """Concatenates N per-scene audio inputs back-to-back (no gaps, no
    overlap - the crossfade is purely visual). Returns (filter_string, label).
    """
    labels_in = "".join(f"[{audio_input_start_index + i}:a]" for i in range(n_scenes))
    return f"{labels_in}concat=n={n_scenes}:v=0:a=1[aout]", "aout"
