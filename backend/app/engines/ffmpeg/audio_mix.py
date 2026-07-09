"""Background-music ducking — specs/04-tasks/task-16-music-subtitle-styles.md.

`sidechaincompress` ducks the music track based on the narration's own
amplitude (louder narration -> more music suppression); a flat pre-
attenuation sets the baseline "quiet" level so music is never intrusive
even in gaps between phrases. Loudnorm still runs last in the overall
finishing chain (in the assemble/finalize stage that calls this), per the
task's own Implementation notes - this filter only produces the mixed,
pre-loudnorm stream.
"""

# Baseline attenuation before ducking - "~-18 dB under narration" is the
# ducked target, achieved by this flat cut plus the sidechain compressor's
# own reduction while narration is actually playing.
MUSIC_BASELINE_DB = -12.0
DUCK_THRESHOLD = 0.05
DUCK_RATIO = 8
DUCK_ATTACK_MS = 5
DUCK_RELEASE_MS = 300
FADE_OUT_S = 1.5


def build_music_duck_filter(
    music_label: str,
    narration_label: str,
    duration_s: float,
    output_label: str = "aout",
) -> str:
    """Ducks `music_label` under `narration_label` and mixes the two into
    a single `output_label` stream. Both inputs are expected already
    trimmed/looped to `duration_s` (music via input_music_looped).

    `narration_label` is used twice below (once as the sidechain trigger,
    once as the actual signal to mix back in) - an ffmpeg filtergraph
    label is consumed the first time it's used as an input, so it must be
    `asplit` into two copies first or the second reference fails with
    "matches no streams" (found by actually running this, not by reading
    the filter docs).
    """
    fade_start = max(0.0, duration_s - FADE_OUT_S)
    return (
        f"[{narration_label}]asplit=2[narr_trigger][narr_out];"
        f"[{music_label}]volume={MUSIC_BASELINE_DB}dB[quiet];"
        f"[quiet][narr_trigger]sidechaincompress="
        f"threshold={DUCK_THRESHOLD}:ratio={DUCK_RATIO}:"
        f"attack={DUCK_ATTACK_MS}:release={DUCK_RELEASE_MS}[ducked];"
        f"[ducked]afade=t=out:st={fade_start:.3f}:d={FADE_OUT_S}[faded];"
        f"[faded][narr_out]amix=inputs=2:duration=first:dropout_transition=0[{output_label}]"
    )
