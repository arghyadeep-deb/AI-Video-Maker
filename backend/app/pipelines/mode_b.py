"""render_mode_b pipeline — specs/03-design/05-mode-b-pipeline.md.

Five stages: tts -> images -> subtitles -> assemble -> finalize. Filesystem
layout per specs/03-design/08-data-model.md:
    media/users/<uid>/projects/<id>/{audio/,images/,subs/,output.mp4,credits.txt}

Personal voice (task-18, OpenVoice conversion) defaults every render to
the user's own enrolled voice via `make_narration_engine` - stock edge-tts
only ever narrates when no profile is enrolled or conversion fails, per
specs/01-requirements/11-personal-voice.md's "stock voice only with a
visible notice" fallback rule (recorded per-scene in the audio
media_asset's own meta_json: `stock_fallback`/`fallback_reason`).
"""
import json
from pathlib import Path

from app.core.config import get_settings
from app.core.ids import new_id
from app.db.connection import get_connection
from app.engines.ffmpeg.audio_mix import build_music_duck_filter
from app.engines.ffmpeg.builder import FFmpegCommand, input_audio, input_image_looped, input_music_looped
from app.engines.ffmpeg.kenburns import (
    SceneClip,
    build_audio_concat_filter,
    build_kenburns_filter_complex,
    total_timeline_duration_s,
)
from app.engines.ffmpeg.progress import FFmpegError, run_with_progress
from app.engines.images.genai_fallback import GenaiFallbackImages
from app.engines.images.pexels import PexelsImages
from app.engines.images.pixabay import PixabayImages
from app.engines.script_llm import ScriptLLM
from app.engines.tts.base import WordTiming
from app.engines.tts.edge import EdgeTTSEngine
from app.jobs.registry import JobContext, register_pipeline
from app.models.script import Scene
from app.pipelines.common import PipelineError, load_project_and_scenes, make_narration_engine, project_dir
from app.services import image_service, music_library, subtitles
from app.services.ffmpeg.probe import ffmpeg_path, probe_duration_s
from app.services.script_repo import get_latest_version_row
from app.services.thumbnails import write_video_frame_thumbnail

ModeBError = PipelineError
_project_dir = project_dir
_load_project_and_scenes = load_project_and_scenes


def _default_voice(language: str) -> str:
    return get_settings().voice_table[language]["female"]


def _upsert_media_asset(conn, project_id: str, kind: str, scene_id: int | None, path: Path, meta: dict) -> None:
    existing = conn.execute(
        "SELECT id FROM media_assets WHERE project_id = ? AND kind = ? AND scene_id IS ?",
        (project_id, kind, scene_id),
    ).fetchone()
    meta_json = json.dumps(meta, ensure_ascii=False)
    if existing is not None:
        conn.execute(
            "UPDATE media_assets SET path = ?, meta_json = ? WHERE id = ?",
            (str(path), meta_json, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO media_assets (id, project_id, kind, scene_id, path, meta_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (new_id(), project_id, kind, scene_id, str(path), meta_json),
        )
    conn.commit()


def make_tts_engine():
    """Overridden in tests (FakeTTSEngine) - kept as a module-level factory
    so stage_tts doesn't need its own engine parameter threaded through the
    registry.Pipeline `(stage_name, coroutine)` shape.
    """
    return EdgeTTSEngine()


def make_pexels_engine(settings):
    return PexelsImages(api_key=settings.pexels_api_key)


def make_pixabay_engine(settings):
    return PixabayImages(api_key=settings.pixabay_api_key)


def make_genai_image_engine(settings):
    return GenaiFallbackImages(api_key=settings.gemini_api_key, model=settings.avatar_styling_model)


async def stage_tts(ctx: JobContext) -> None:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        project, scenes = _load_project_and_scenes(conn, project_id)
        voice_id = project["voice"] or _default_voice(project["language"])
        if not project["voice"]:
            conn.execute("UPDATE projects SET voice = ? WHERE id = ?", (voice_id, project_id))
            conn.commit()

        audio_dir = _project_dir(settings.media_root, project["user_id"], project_id) / "audio"
        engine = make_narration_engine(conn, project["user_id"], make_tts_engine())

        for i, scene in enumerate(scenes):
            if ctx.cancelled():
                return
            out_path = audio_dir / f"scene-{scene.id}.mp3"
            result = await engine.speak(scene.text, voice_id, out_path)
            _upsert_media_asset(
                conn, project_id, "audio", scene.id, out_path,
                {
                    "voice": voice_id, "word_count": len(result.timings),
                    "stock_fallback": engine.used_stock_fallback,
                    "fallback_reason": engine.fallback_reason,
                },
            )
            ctx.report((i + 1) / len(scenes) * 100)
    finally:
        conn.close()


async def stage_images(ctx: JobContext) -> None:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        project, scenes = _load_project_and_scenes(conn, project_id)

        if any(s.visual_hint_stale for s in scenes):
            llm = ScriptLLM(api_key=settings.gemini_api_key, model=settings.script_llm_model)
            scenes = await image_service.refresh_stale_hints(llm, scenes)

        images_dir = _project_dir(settings.media_root, project["user_id"], project_id) / "images"
        pexels = make_pexels_engine(settings)
        pixabay = make_pixabay_engine(settings)
        genai = make_genai_image_engine(settings)

        await image_service.source_project_images(
            conn, project_id, scenes, project["format"], images_dir, pexels, pixabay, genai
        )
        ctx.report(100)
    finally:
        conn.close()


async def stage_subtitles(ctx: JobContext) -> None:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        project, scenes = _load_project_and_scenes(conn, project_id)
        project_dir = _project_dir(settings.media_root, project["user_id"], project_id)

        all_words: list[subtitles.WordCue] = []
        cumulative_ms = 0
        for scene in scenes:
            timings_path = (project_dir / "audio" / f"scene-{scene.id}.mp3").with_suffix(".timings.json")
            raw_timings = json.loads(timings_path.read_text(encoding="utf-8"))
            word_timings = [WordTiming(**t) for t in raw_timings]
            all_words.extend(
                subtitles.realign_with_source_text(scene.text, word_timings, scene_offset_ms=cumulative_ms)
            )
            scene_duration_ms = (
                (word_timings[-1].offset_ms + word_timings[-1].duration_ms) if word_timings else 0
            )
            cumulative_ms += scene_duration_ms

        phrases = subtitles.group_into_phrases(all_words)
        subs_dir = project_dir / "subs"
        subs_dir.mkdir(parents=True, exist_ok=True)
        karaoke = ctx.payload.get("subtitle_style", "phrase") == "karaoke"
        ass_content = subtitles.write_ass(phrases, project["language"], project["format"], karaoke=karaoke)
        srt_content = subtitles.write_srt(phrases)
        (subs_dir / "subtitles.ass").write_text(ass_content, encoding="utf-8")
        (subs_dir / "subtitles.srt").write_text(srt_content, encoding="utf-8")

        _upsert_media_asset(
            conn, project_id, "subtitle", None, subs_dir / "subtitles.ass", {"phrases": len(phrases)}
        )
        ctx.report(100)
    finally:
        conn.close()


def _scene_duration_s(project_dir: Path, scene: Scene) -> float:
    timings_path = (project_dir / "audio" / f"scene-{scene.id}.mp3").with_suffix(".timings.json")
    raw = json.loads(timings_path.read_text(encoding="utf-8"))
    if not raw:
        return 0.0
    last = raw[-1]
    return (last["offset_ms"] + last["duration_ms"]) / 1000


def _escaped_ffmpeg_path(path: Path) -> str:
    """ffmpeg's filtergraph parser splits on ':' - a bare Windows drive
    letter colon (C:) breaks it, so escape it. Also used for the ass=
    filename itself: it must be an absolute path since the ffmpeg
    subprocess's cwd is not the project directory.
    """
    posix = str(path).replace("\\", "/")
    if len(posix) > 1 and posix[1] == ":":
        posix = posix[0] + "\\:" + posix[2:]
    return posix


FORMAT_RESOLUTION = {"9x16": (1080, 1920), "16x9": (1920, 1080)}


async def stage_assemble(ctx: JobContext) -> None:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        project, scenes = _load_project_and_scenes(conn, project_id)
        project_dir = _project_dir(settings.media_root, project["user_id"], project_id)
        width, height = FORMAT_RESOLUTION[project["format"]]

        durations = [_scene_duration_s(project_dir, s) for s in scenes]
        clips = [
            SceneClip(index=i, image_path=str(project_dir / "images" / f"scene-{s.id}.jpg"), duration_s=d)
            for i, (s, d) in enumerate(zip(scenes, durations))
        ]

        video_filter, video_label = build_kenburns_filter_complex(clips, width, height)
        audio_filter, audio_label = build_audio_concat_filter(len(scenes), audio_input_start_index=len(scenes))

        ass_path = (project_dir / "subs" / "subtitles.ass").resolve()
        fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
        subbed_label = "vsub"
        subtitle_filter = (
            f"[{video_label}]ass='{_escaped_ffmpeg_path(ass_path)}':"
            f"fontsdir='{_escaped_ffmpeg_path(fonts_dir)}'[{subbed_label}]"
        )

        filters = [video_filter, audio_filter, subtitle_filter]
        image_inputs = [
            input_image_looped(Path(c.image_path).resolve(), _padded_duration(c, len(clips)))
            for c in clips
        ]
        audio_inputs = [
            input_audio((project_dir / "audio" / f"scene-{s.id}.mp3").resolve()) for s in scenes
        ]
        total_duration = total_timeline_duration_s(durations)

        music_track = None
        final_audio_label = audio_label
        if ctx.payload.get("music_enabled") and ctx.payload.get("music_mood"):
            music_track = music_library.pick_track(ctx.payload["music_mood"])
        if music_track is not None:
            music_input_index = len(image_inputs) + len(audio_inputs)
            music_inputs = [input_music_looped(Path(music_track["path"]), total_duration)]
            mixed_label = "amixed"
            filters.append(
                build_music_duck_filter(f"{music_input_index}:a", audio_label, total_duration, mixed_label)
            )
            final_audio_label = mixed_label
        else:
            music_inputs = []

        filter_complex = ";".join(filters)

        raw_output = project_dir / "raw_assembled.mp4"
        command = FFmpegCommand(
            inputs=image_inputs + audio_inputs + music_inputs,
            filter_complex=filter_complex,
            maps=["-map", f"[{subbed_label}]", "-map", f"[{final_audio_label}]"],
            output_args=["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"],
            output_path=str(raw_output.resolve()),
        )

        def report(pct: float) -> None:
            ctx.report(pct)

        ffmpeg_bin = ffmpeg_path()
        if ffmpeg_bin is None:
            raise ModeBError("ffmpeg not found on PATH")

        try:
            await run_with_progress(
                command.to_args(ffmpeg_bin),
                total_duration,
                report,
                register_process=ctx.register_process,
            )
        except FFmpegError as exc:
            raise ModeBError(str(exc)) from exc

        if music_track is not None:
            # Recorded here (not re-picked in stage_finalize) so credits.txt
            # reflects the exact track actually mixed in, not a second
            # random draw - specs/04-tasks/task-16-music-subtitle-styles.md:
            # "Track choice recorded in media_assets.meta_json + credits.txt".
            _upsert_media_asset(
                conn, project_id, "music", None, Path(music_track["path"]),
                {
                    "filename": music_track["filename"], "mood": music_track["mood"],
                    "title": music_track.get("title", music_track["filename"]),
                    "artist": music_track.get("artist", "Unknown"),
                },
            )
    finally:
        conn.close()


def _padded_duration(clip: SceneClip, n_scenes: int) -> float:
    from app.engines.ffmpeg.kenburns import clip_render_duration

    return clip_render_duration(clip.index, n_scenes, clip.duration_s)


async def stage_finalize(ctx: JobContext) -> None:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        project, scenes = _load_project_and_scenes(conn, project_id)
        project_dir = _project_dir(settings.media_root, project["user_id"], project_id)

        raw_output = project_dir / "raw_assembled.mp4"
        final_output = project_dir / "output.mp4"

        ffmpeg_bin = ffmpeg_path()
        if ffmpeg_bin is None:
            raise ModeBError("ffmpeg not found on PATH")

        command = FFmpegCommand(
            inputs=[["-i", str(raw_output.resolve())]],
            output_args=[
                "-af", "loudnorm",
                "-c:v", "copy",
                "-movflags", "+faststart",
                "-metadata", "comment=AI-generated",
            ],
            output_path=str(final_output.resolve()),
        )

        def report(pct: float) -> None:
            ctx.report(pct * 0.8)  # leave the last 20% for credits.txt + DB update

        try:
            await run_with_progress(
                command.to_args(ffmpeg_bin), 1.0, report, register_process=ctx.register_process
            )
        except FFmpegError as exc:
            raise ModeBError(str(exc)) from exc

        raw_output.unlink(missing_ok=True)

        _write_credits(conn, project_id, project_dir)

        duration_s = probe_duration_s(final_output) or 1.0
        write_video_frame_thumbnail(final_output, project_dir / "thumbnail.jpg", duration_s)

        conn.execute(
            "UPDATE projects SET status = 'done', output_path = ? WHERE id = ?",
            (str(final_output), project_id),
        )
        conn.commit()
        ctx.report(100)
    finally:
        conn.close()


def _write_credits(conn, project_id: str, project_dir: Path) -> None:
    rows = conn.execute(
        "SELECT * FROM media_assets WHERE project_id = ? AND kind = 'image' ORDER BY scene_id",
        (project_id,),
    ).fetchall()
    lines = ["Image credits", "=" * 40, ""]
    for row in rows:
        meta = json.loads(row["meta_json"] or "{}")
        if meta.get("engine") == "genai":
            lines.append(f"Scene {row['scene_id']}: AI-generated (Gemini 2.5 Flash Image)")
        else:
            photographer = meta.get("photographer") or "Unknown"
            source = meta.get("source", "unknown")
            url = meta.get("url", "")
            lines.append(f"Scene {row['scene_id']}: Photo by {photographer} via {source} - {url}")

    music_row = conn.execute(
        "SELECT * FROM media_assets WHERE project_id = ? AND kind = 'music'", (project_id,)
    ).fetchone()
    if music_row is not None:
        meta = json.loads(music_row["meta_json"] or "{}")
        title = meta.get("title", meta.get("filename", "unknown"))
        artist = meta.get("artist", "Unknown")
        lines += [
            "", "Background music", "=" * 40, "",
            f'"{title}" - {artist}',
            "Licensed under CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/)",
        ]

    (project_dir / "credits.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


MODE_B_PIPELINE = [
    ("tts", stage_tts),
    ("images", stage_images),
    ("subtitles", stage_subtitles),
    ("assemble", stage_assemble),
    ("finalize", stage_finalize),
]

register_pipeline("render_mode_b", MODE_B_PIPELINE)
