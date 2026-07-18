"""render_mode_a pipeline — specs/03-design/04-mode-a-pipeline.md.

Three stages: tts -> animate -> assemble. Unlike Mode B (per-scene TTS +
cross-scene subtitle offset stitching), Mode A synthesizes the WHOLE script
as one continuous TTS call - a single timing stream, no scene-boundary math
needed for subtitles.

Filesystem layout: media/users/<uid>/projects/<id>/{audio.mp3, audio.wav,
subs/, raw_animated.mp4, output.mp4, credits.txt} - avatar-driven, no
per-scene images/ directory (Mode B's own layout doesn't apply here).

Personal voice (task-18, OpenVoice conversion) defaults every render to
the user's own enrolled voice via `make_narration_engine`, same as Mode B -
stock edge-tts only narrates when no profile is enrolled or conversion
fails.
"""
import asyncio
import contextlib
import time
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.db.connection import get_connection
from app.engines.ffmpeg.audio_mix import build_music_duck_filter
from app.engines.ffmpeg.builder import FFmpegCommand, input_music_looped
from app.engines.ffmpeg.finishing import build_scale_pad_filter, build_subtitle_filter
from app.engines.ffmpeg.progress import FFmpegError, run_with_progress
from app.engines.talking_head.base import TalkingHeadEngine
from app.engines.talking_head.chooser import render_with_fallback
from app.engines.talking_head.home_worker import HomeWorkerTalkingHeadEngine
from app.engines.talking_head.sadtalker_zerogpu import SadTalkerZeroGPUEngine
from app.engines.talking_head.wav2lip_local import Wav2LipLocalEngine
from app.jobs import gpu_router
from app.engines.tts.edge import EdgeTTSEngine, to_wav16k
from app.jobs.registry import JobContext, register_pipeline
from app.pipelines.common import PipelineError, load_project_and_scenes, make_narration_engine, project_dir
from app.services import music_library, subtitles
from app.services.ffmpeg.probe import ffmpeg_path, probe_duration_s
from app.services.thumbnails import write_portrait_thumbnail

# specs/01-requirements/04-mode-a-avatar.md / 03-design/04-mode-a-pipeline.md:
# "Mode A available for <=2 min scripts; UI steers 5-min scripts to Mode B."
MAX_DURATION_S = 120

FORMAT_RESOLUTION = {"9x16": (1080, 1920), "16x9": (1920, 1080)}

# SadTalker/Wav2Lip give no real progress callback - the animate stage
# estimates elapsed-vs-estimate instead of faking a precise bar (locked in
# specs/03-design/04-mode-a-pipeline.md's "Long-script handling"). This
# multiplier is a conservative guess, not a measured constant; the visible
# bar caps below 100% until the render genuinely finishes either way, so an
# optimistic guess just means the bar sits at ~95% for a bit longer.
ANIMATE_ESTIMATE_MULTIPLIER = 2.0


class ModeAError(PipelineError):
    pass


def make_tts_engine():
    return EdgeTTSEngine()


def make_wav2lip_engine() -> TalkingHeadEngine:
    return Wav2LipLocalEngine()


def make_sadtalker_engine(settings, conn) -> Optional[TalkingHeadEngine]:
    if not settings.sadtalker_space_id:
        return None
    return SadTalkerZeroGPUEngine(
        space_id=settings.sadtalker_space_id,
        hf_token=settings.hf_token,
        conn=conn,
        daily_limit_seconds=settings.zerogpu_daily_seconds,
    )


def make_home_worker_engine(settings, cancelled=None) -> Optional[TalkingHeadEngine]:
    """Tier 1 (task-20a). Always constructed - the engine itself checks
    worker presence per render, so a PC that comes online between two jobs
    is picked up without any config change."""
    return HomeWorkerTalkingHeadEngine(settings.db_path, settings, cancelled=cancelled)


def _default_voice(language: str) -> str:
    return get_settings().voice_table[language]["female"]


def _get_approved_avatar(conn, avatar_id: str, user_id: str):
    avatar = conn.execute(
        "SELECT * FROM avatars WHERE id = ? AND user_id = ?", (avatar_id, user_id)
    ).fetchone()
    if avatar is None:
        raise ModeAError(f"Avatar {avatar_id} not found")
    if not avatar["approved"]:
        raise ModeAError(f"Avatar {avatar_id} is not approved yet")
    return avatar


async def stage_tts(ctx: JobContext) -> None:
    """One TTS call for the whole script - specs/03-design/04-mode-a-pipeline.md:
    "single timing stream -> subtitles when toggle ON" (unlike Mode B, which
    stitches per-scene timings across scene boundaries, there's only one
    scene's worth of text here, so subtitle generation is just this stage's
    tail end, not a separate stage)."""
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        project, scenes = load_project_and_scenes(conn, project_id)
        voice_id = project["voice"] or _default_voice(project["language"])
        if not project["voice"]:
            conn.execute("UPDATE projects SET voice = ? WHERE id = ?", (voice_id, project_id))
            conn.commit()

        full_text = " ".join(scene.text for scene in scenes)
        p_dir = project_dir(settings.media_root, project["user_id"], project_id)
        audio_path = p_dir / "audio.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)

        # Narration-fallback status isn't persisted here (Mode A's `jobs.engine_notes`
        # column is already owned by stage_animate's talking-head-engine note,
        # which would overwrite it - a real conflict found while wiring this
        # up, not a hypothetical). The primary "explicit notice" mechanism for
        # both modes is the generate page checking GET /api/voices before
        # rendering at all; see task-18 Completion notes for the scope call.
        engine = make_narration_engine(conn, project["user_id"], make_tts_engine())
        speech_result = await engine.speak(full_text, voice_id, audio_path)
        ctx.report(70)

        if bool(ctx.payload.get("subtitles", True)):
            words = subtitles.realign_with_source_text(full_text, speech_result.timings)
            phrases = subtitles.group_into_phrases(words)
            subs_dir = p_dir / "subs"
            subs_dir.mkdir(parents=True, exist_ok=True)
            subtitle_style = ctx.payload.get("subtitle_style", "phrase")
            (subs_dir / "subtitles.ass").write_text(
                subtitles.write_ass(phrases, project["language"], project["format"], style_name=subtitle_style),
                encoding="utf-8",
            )
            (subs_dir / "subtitles.srt").write_text(subtitles.write_srt(phrases), encoding="utf-8")

        ctx.report(100)
    finally:
        conn.close()


async def stage_animate(ctx: JobContext) -> None:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        project, _ = load_project_and_scenes(conn, project_id)
        avatar_id = ctx.payload["avatar_id"]
        avatar = _get_approved_avatar(conn, avatar_id, project["user_id"])

        p_dir = project_dir(settings.media_root, project["user_id"], project_id)
        audio_path = p_dir / "audio.mp3"
        wav_path = to_wav16k(audio_path)

        # None = server decides: HD by default while the home worker is
        # online with a sadtalker engine loaded (specs/03-design/11-gpu-worker.md);
        # an explicit user choice from the UI always wins.
        hd_requested = ctx.payload.get("hd_requested")
        if hd_requested is None:
            hd_requested = "sadtalker" in gpu_router.worker_capabilities(conn, settings)
        hd_requested = bool(hd_requested)
        wav2lip_engine = make_wav2lip_engine()
        sadtalker_engine = make_sadtalker_engine(settings, conn)
        home_engine = make_home_worker_engine(settings, cancelled=ctx.cancelled)

        raw_output = p_dir / "raw_animated.mp4"
        audio_duration_s = probe_duration_s(wav_path) or 30.0
        estimated_total_s = audio_duration_s * ANIMATE_ESTIMATE_MULTIPLIER

        async def _tick_progress() -> None:
            start = time.monotonic()
            while True:
                await asyncio.sleep(1.0)
                elapsed = time.monotonic() - start
                ctx.report(min(95.0, (elapsed / estimated_total_s) * 100))

        ticker = asyncio.create_task(_tick_progress())
        try:
            result = await render_with_fallback(
                hd_requested,
                sadtalker_engine,
                wav2lip_engine,
                str(avatar["portrait_path"]),
                str(wav_path),
                str(raw_output),
                home_engine=home_engine,
            )
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker

        conn.execute(
            "UPDATE jobs SET engine_notes = ? WHERE id = ?", (result.engine, ctx.job_id)
        )
        conn.commit()
        ctx.report(100)
    finally:
        conn.close()


async def stage_assemble(ctx: JobContext) -> None:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        project, _ = load_project_and_scenes(conn, project_id)
        p_dir = project_dir(settings.media_root, project["user_id"], project_id)
        target_width, target_height = FORMAT_RESOLUTION[project["format"]]

        raw_animated = p_dir / "raw_animated.mp4"
        wav_path = p_dir / "audio.wav"

        ffmpeg_bin = ffmpeg_path()
        if ffmpeg_bin is None:
            raise ModeAError("ffmpeg not found on PATH")

        src_probe = _probe_video_dims(raw_animated)
        video_filter = build_scale_pad_filter(
            src_probe[0], src_probe[1], target_width, target_height,
            input_label="0:v", output_label="scaled",
        )
        final_video_label = "scaled"
        filters = [video_filter]

        subtitles_on = bool(ctx.payload.get("subtitles", True))
        audio_label = "0:a"

        if subtitles_on:
            ass_path = (p_dir / "subs" / "subtitles.ass")
            if ass_path.exists():
                subs_dir = p_dir / "subs"
                subs_dir.mkdir(parents=True, exist_ok=True)
                fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
                subtitle_filter = build_subtitle_filter(
                    ass_path.resolve(), fonts_dir, input_label="scaled", output_label="vsub"
                )
                filters.append(subtitle_filter)
                final_video_label = "vsub"

        total_duration = probe_duration_s(raw_animated) or 30.0

        music_track = None
        if ctx.payload.get("music_enabled") and ctx.payload.get("music_mood"):
            music_track = music_library.pick_track(ctx.payload["music_mood"])
        music_inputs: list[list[str]] = []
        if music_track is not None:
            music_inputs = [input_music_looped(Path(music_track["path"]), total_duration)]
            mixed_label = "amixed"
            filters.append(build_music_duck_filter("1:a", audio_label, total_duration, mixed_label))
            audio_label = mixed_label

        maps = ["-map", f"[{final_video_label}]", "-map", f"[{audio_label}]" if music_track else audio_label]

        raw_output = p_dir / "raw_assembled.mp4"
        command = FFmpegCommand(
            inputs=[["-i", str(raw_animated.resolve())], *music_inputs],
            filter_complex=";".join(filters),
            maps=maps,
            output_args=["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"],
            output_path=str(raw_output.resolve()),
        )

        def report(pct: float) -> None:
            ctx.report(pct)

        try:
            await run_with_progress(
                command.to_args(ffmpeg_bin), total_duration, report,
                register_process=ctx.register_process,
            )
        except FFmpegError as exc:
            raise ModeAError(str(exc)) from exc

        avatar_id = ctx.payload["avatar_id"]
        await _finalize(conn, project_id, p_dir, raw_output, ffmpeg_bin, avatar_id, music_track, ctx)
    finally:
        conn.close()


def _probe_video_dims(path: Path) -> tuple[int, int]:
    import shutil
    import subprocess

    # Deriving ffprobe from ffmpeg_bin via string replace is unsafe - on a
    # real install (e.g. .../ffmpeg-8.1.2-full_build/bin/ffmpeg.exe) the
    # substring "ffmpeg" also appears in the *directory* name, corrupting
    # the path. Look ffprobe up independently instead.
    ffprobe_bin = shutil.which("ffprobe")
    if ffprobe_bin is None:
        raise ModeAError("ffprobe not found on PATH")
    result = subprocess.run(
        [
            ffprobe_bin, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path),
        ],
        capture_output=True, text=True, timeout=10, check=True,
    )
    width_str, height_str = result.stdout.strip().split("x")
    return int(width_str), int(height_str)


async def _finalize(
    conn, project_id: str, p_dir: Path, raw_output: Path, ffmpeg_bin: str, avatar_id: str,
    music_track: Optional[dict], ctx: JobContext,
) -> None:
    final_output = p_dir / "output.mp4"
    command = FFmpegCommand(
        inputs=[["-i", str(raw_output.resolve())]],
        output_args=[
            "-af", "loudnorm", "-c:v", "copy", "-movflags", "+faststart",
            "-metadata", "comment=AI-generated",
        ],
        output_path=str(final_output.resolve()),
    )
    try:
        await run_with_progress(
            command.to_args(ffmpeg_bin), 1.0, lambda _pct: None,
            register_process=ctx.register_process,
        )
    except FFmpegError as exc:
        raise ModeAError(str(exc)) from exc

    raw_output.unlink(missing_ok=True)
    _write_credits(p_dir, music_track)

    # Portrait, not a frame-grab - it already represents the video, per
    # specs/04-tasks/task-13-library-delivery.md's own "portrait (Mode A
    # pre-render)" note.
    avatar = conn.execute("SELECT portrait_path FROM avatars WHERE id = ?", (avatar_id,)).fetchone()
    if avatar and avatar["portrait_path"]:
        write_portrait_thumbnail(Path(avatar["portrait_path"]), p_dir / "thumbnail.jpg")

    conn.execute(
        "UPDATE projects SET status = 'done', output_path = ? WHERE id = ?",
        (str(final_output), project_id),
    )
    conn.commit()
    ctx.report(100)


def _write_credits(project_dir_path: Path, music_track: Optional[dict]) -> None:
    lines = ["Talking-head avatar generated with Wav2Lip / SadTalker."]
    if music_track is not None:
        title = music_track.get("title", music_track["filename"])
        artist = music_track.get("artist", "Unknown")
        lines += [
            "", "Background music", "=" * 40, "",
            f'"{title}" - {artist}',
            "Licensed under CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/)",
        ]
    (project_dir_path / "credits.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


MODE_A_PIPELINE = [
    ("tts", stage_tts),
    ("animate", stage_animate),
    ("assemble", stage_assemble),
]

register_pipeline("render_mode_a", MODE_A_PIPELINE)
