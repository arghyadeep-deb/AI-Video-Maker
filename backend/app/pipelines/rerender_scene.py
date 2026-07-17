"""render_mode_b post-render fix-ups — specs/04-tasks/task-17-post-render-tools.md.

Deviation from the task's literal "surgical re-splice with cached
segments" wording: `mode_b.build_kenburns_filter_complex` chains every
scene through one single-pass ffmpeg filtergraph (xfade crossfades +
audio concat, cumulative-offset timing) rather than per-scene rendered
segment files - splitting that into a genuinely segment-cacheable
architecture would touch already-shipped, heavily-tested render code
(task-09/12) for a 1-2 user site where a full reassemble of a 30-120s
video is already fast. Instead: only the ONE touched scene's TTS/image is
actually re-sourced (everything else's underlying files are untouched,
so the reassemble step is a deterministic re-run of the exact same
zoompan/xfade filters over the exact same untouched inputs for every
other scene - proven pixel-identical by
tests/test_rerender_scene_pipeline.py's frame-hash comparison), then the
existing `mode_b.stage_subtitles` / `stage_assemble` / `stage_finalize`
stages are reused as-is for the reassemble.
"""
import json

from app.core.config import get_settings
from app.db.connection import get_connection
from app.jobs.registry import JobContext, register_pipeline
from app.pipelines import mode_b
from app.pipelines.common import load_project_and_scenes, project_dir
from app.services import image_service


async def stage_scene_tts(ctx: JobContext) -> None:
    """Re-runs TTS for exactly one scene (a scene-rerender request,
    optionally with a new voice) - a no-op for a pure image-swap request,
    which never sets `retts`, so every other scene's audio.mp3 is left
    byte-for-byte untouched."""
    if not ctx.payload.get("retts"):
        return
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        scene_id = ctx.payload["scene_id"]
        project, scenes = load_project_and_scenes(conn, project_id)
        scene = next(s for s in scenes if s.id == scene_id)

        voice_id = ctx.payload.get("voice") or project["voice"] or mode_b._default_voice(project["language"])
        if ctx.payload.get("voice") and ctx.payload["voice"] != project["voice"]:
            conn.execute("UPDATE projects SET voice = ? WHERE id = ?", (voice_id, project_id))
            conn.commit()

        audio_dir = project_dir(settings.media_root, project["user_id"], project_id) / "audio"
        engine = mode_b.make_tts_engine()
        out_path = audio_dir / f"scene-{scene.id}.mp3"
        result = await engine.speak(scene.text, voice_id, out_path)
        mode_b._upsert_media_asset(
            conn, project_id, "audio", scene.id, out_path,
            {"voice": voice_id, "word_count": len(result.timings)},
        )
        ctx.report(100)
    finally:
        conn.close()


async def stage_scene_image(ctx: JobContext) -> None:
    """Re-sources exactly one scene's image via the normal fallback chain
    (stock -> genai, same cap) - a no-op when the caller already wrote the
    new image directly (the swap-image endpoint downloads/generates the
    picked candidate synchronously before enqueueing, since it's a single
    small request), and only set for a plain scene-rerender."""
    if not ctx.payload.get("resource_image"):
        return
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        project_id = ctx.payload["project_id"]
        scene_id = ctx.payload["scene_id"]
        project, scenes = load_project_and_scenes(conn, project_id)
        scene = next(s for s in scenes if s.id == scene_id)

        already_used: set[str] = set()
        for row in conn.execute(
            "SELECT meta_json FROM media_assets WHERE project_id = ? AND kind = 'image' AND scene_id != ?",
            (project_id, scene_id),
        ):
            meta = json.loads(row["meta_json"] or "{}")
            if meta.get("source_id"):
                already_used.add(meta["source_id"])

        images_dir = project_dir(settings.media_root, project["user_id"], project_id) / "images"
        flux = mode_b.make_flux_engine(settings)
        pexels = mode_b.make_pexels_engine(settings)
        pixabay = mode_b.make_pixabay_engine(settings)
        genai = mode_b.make_genai_image_engine(settings)

        candidate, engine_used, alternates = await image_service.source_scene_image_with_alternates(
            conn, scene, project["format"], already_used, flux, pexels, pixabay, genai
        )
        out_path = images_dir / f"scene-{scene.id}.jpg"
        await image_service.download_candidate(candidate, out_path)
        meta = image_service._credit_meta(candidate, engine_used, alternates)
        mode_b._upsert_media_asset(conn, project_id, "image", scene.id, out_path, meta)
        # A re-sourced image invalidates any generated-footage clip made
        # from the old one - this scene falls back to Ken Burns (task-20a).
        mode_b.delete_scene_clip(conn, project_id, scene_id)
        ctx.report(100)
    finally:
        conn.close()


RERENDER_SCENE_PIPELINE = [
    ("retts", stage_scene_tts),
    ("resource_image", stage_scene_image),
    ("subtitles", mode_b.stage_subtitles),
    ("assemble", mode_b.stage_assemble),
    ("finalize", mode_b.stage_finalize),
]

register_pipeline("rerender_scene", RERENDER_SCENE_PIPELINE)
