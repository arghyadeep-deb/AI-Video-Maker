"""specs/03-design/09-api-endpoints.md — Generation & jobs."""
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse

from app.api.projects import get_owned_project
from app.core.config import get_settings
from app.core.deps import get_current_user_id, get_db
from app.core.errors import AppError, NotFoundError
from app.core.ids import new_id
from app.jobs import queue as job_queue
from app.pipelines import mode_a  # noqa: F401 - import registers "render_mode_a"
from app.pipelines import mode_b  # noqa: F401 - import registers "render_mode_b"
from app.pipelines import rerender_scene  # noqa: F401 - import registers "rerender_scene"
from app.jobs.worker import Worker
from app.models.image import ImageCandidate
from app.models.job import JobOut
from app.models.postrender import (
    CandidateOut,
    RerenderOtherModeOut,
    RerenderOtherModeRequest,
    SceneCandidatesOut,
    SceneRerenderRequest,
    SwapImageRequest,
)
from app.models.video import VideoRequest
from app.pipelines.common import load_project_and_scenes, project_dir as _project_dir
from app.quota import guards
from app.services import image_service
from app.services.job_repo import row_to_job as _row_to_job
from app.services.project_repo import effective_status

router = APIRouter()

# specs/03-design/04-mode-a-pipeline.md: "Mode A available for <=2 min
# scripts; UI steers 5-min scripts to Mode B." Enforced at the API too, not
# just the UI, per the task's own Implementation notes.
MODE_A_MAX_DURATION_S = 120


def get_worker(request: Request) -> Worker:
    return request.app.state.worker


@router.post("/{project_id}/video", response_model=JobOut, status_code=201)
def create_render_job(
    project_id: str,
    payload: VideoRequest,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> JobOut:
    project = get_owned_project(conn, project_id, user_id)
    # A project's raw `status` column never reverts once it flips to
    # "generating" - if the render that put it there later failed or got
    # aborted (e.g. a server restart), the accepted script is still valid
    # and the user should be able to retry, not get permanently stuck.
    status = effective_status(conn, project_id, project["status"])
    if status not in ("accepted", "failed", "cancelled"):
        raise AppError(
            "Script must be accepted before generating a video", hint="Accept the script first"
        )

    if payload.voice:
        valid_voices = set(get_settings().voice_table.get(project["language"], {}).values())
        if payload.voice not in valid_voices:
            raise AppError(
                "Unknown voice for this project's language", hint="Pick one of the offered voices"
            )
        conn.execute("UPDATE projects SET voice = ? WHERE id = ?", (payload.voice, project_id))

    if payload.mode == "a":
        if project["duration_s"] > MODE_A_MAX_DURATION_S:
            raise AppError(
                "This script is too long for Mode A",
                hint="Avatar videos are limited to 2 minutes - use Image Video (Mode B) for longer scripts",
            )
        if not payload.avatar_id:
            raise AppError("An avatar is required for Mode A", hint="Pick or create an avatar first")
        avatar = conn.execute(
            "SELECT * FROM avatars WHERE id = ? AND user_id = ?", (payload.avatar_id, user_id)
        ).fetchone()
        if avatar is None:
            raise NotFoundError(f"Avatar {payload.avatar_id} not found")
        if not avatar["approved"]:
            raise AppError("This avatar hasn't been approved yet", hint="Approve the portrait first")

        job_id = job_queue.enqueue(
            conn, user_id, project_id, "render_mode_a",
            {
                "project_id": project_id,
                "avatar_id": payload.avatar_id,
                "subtitles": payload.subtitles,
                "subtitle_style": payload.subtitle_style,
                "hd_requested": payload.hd_requested,
                "music_enabled": payload.music_enabled,
                "music_mood": payload.music_mood,
            },
        )
        conn.execute(
            "UPDATE projects SET status = 'generating', mode = 'a' WHERE id = ?", (project_id,)
        )
    else:
        # No upfront availability gate for visual_level="footage" anymore
        # (task-23): the old assumption - "only offered while the GPU worker
        # is online" - predates stage_footage's own public-Space tier
        # (backend/app/engines/scene_gen/ltx_public.py), which has no
        # availability precondition of its own. The pipeline's existing
        # per-scene fallback chain (public Space -> home worker -> Ken
        # Burns) already degrades honestly if every tier fails; rejecting
        # the request up front here would just be stale and wrong now.
        job_id = job_queue.enqueue(
            conn, user_id, project_id, "render_mode_b",
            {
                "project_id": project_id,
                "subtitle_style": payload.subtitle_style,
                "music_enabled": payload.music_enabled,
                "music_mood": payload.music_mood,
                "visual_level": payload.visual_level,
            },
        )
        conn.execute(
            "UPDATE projects SET status = 'generating', mode = 'b' WHERE id = ?", (project_id,)
        )

    conn.commit()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(conn, row)


@router.get("/{project_id}/video")
def stream_video(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    project = get_owned_project(conn, project_id, user_id)
    if not project["output_path"]:
        raise NotFoundError("No rendered video yet for this project")
    return FileResponse(project["output_path"], media_type="video/mp4")


@router.get("/{project_id}/video/download")
def download_video(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    project = get_owned_project(conn, project_id, user_id)
    if not project["output_path"]:
        raise NotFoundError("No rendered video yet for this project")

    project_dir = Path(project["output_path"]).parent
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(project["output_path"], arcname="video.mp4")
        srt_path = project_dir / "subs" / "subtitles.srt"
        if srt_path.exists():
            zf.write(srt_path, arcname="subtitles.srt")
        credits_path = project_dir / "credits.txt"
        if credits_path.exists():
            zf.write(credits_path, arcname="credits.txt")
    buffer.seek(0)

    safe_title = (project["title"] or "video").replace(" ", "_")
    # Titles are frequently Devanagari (this is a Hindi/English product) -
    # HTTP header values must be Latin-1, so a bare non-ASCII filename
    # crashes with UnicodeEncodeError. RFC 6266 filename* carries the real
    # UTF-8 name; filename= stays a plain-ASCII fallback for older clients.
    ascii_fallback = safe_title.encode("ascii", errors="ignore").decode("ascii").strip("_") or "video"
    content_disposition = (
        f'attachment; filename="{ascii_fallback}.zip"; '
        f"filename*=UTF-8''{quote(safe_title)}.zip"
    )
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition},
    )


def _get_scene_image_row(conn: sqlite3.Connection, project: sqlite3.Row, scene_id: int) -> sqlite3.Row:
    if project["mode"] != "b":
        raise AppError(
            "Only Image Video (Mode B) projects have scene images",
            hint="This project doesn't have per-scene images to swap",
        )
    row = conn.execute(
        "SELECT * FROM media_assets WHERE project_id = ? AND kind = 'image' AND scene_id = ?",
        (project["id"], scene_id),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"No image found for scene {scene_id}")
    return row


@router.get("/{project_id}/scenes/{scene_id}/image")
def get_scene_image(
    project_id: str,
    scene_id: int,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    project = get_owned_project(conn, project_id, user_id)
    row = _get_scene_image_row(conn, project, scene_id)
    return FileResponse(row["path"], media_type="image/jpeg")


@router.get("/{project_id}/scenes/{scene_id}/candidates", response_model=SceneCandidatesOut)
def get_scene_candidates(
    project_id: str,
    scene_id: int,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> SceneCandidatesOut:
    project = get_owned_project(conn, project_id, user_id)
    row = _get_scene_image_row(conn, project, scene_id)
    meta = json.loads(row["meta_json"] or "{}")

    current = CandidateOut(
        source=meta.get("source", meta.get("engine", "unknown")),
        source_id=meta.get("source_id", ""),
        width=meta.get("width"),
        height=meta.get("height"),
        url=meta.get("url"),
        photographer=meta.get("photographer"),
        photographer_url=meta.get("photographer_url"),
    )
    alternates = [CandidateOut(**alt) for alt in meta.get("alternates", [])]
    settings = get_settings()
    can_generate_new = guards.usage_today(conn, "genai_image") < settings.genai_image_daily_cap
    return SceneCandidatesOut(current=current, alternates=alternates, can_generate_new=can_generate_new)


@router.post("/{project_id}/scenes/{scene_id}/image", response_model=JobOut, status_code=201)
async def swap_scene_image(
    project_id: str,
    scene_id: int,
    payload: SwapImageRequest,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> JobOut:
    project = get_owned_project(conn, project_id, user_id)
    row = _get_scene_image_row(conn, project, scene_id)
    meta = json.loads(row["meta_json"] or "{}")

    settings = get_settings()
    images_dir = _project_dir(settings.media_root, user_id, project_id) / "images"
    out_path = images_dir / f"scene-{scene_id}.jpg"

    if payload.generate_new:
        # visual_hint isn't carried in media_assets meta - read it from the
        # accepted script instead.
        _project_row, scenes = load_project_and_scenes(conn, project_id)
        scene = next(s for s in scenes if s.id == scene_id)

        genai = mode_b.make_genai_image_engine(settings)
        guards.guard(conn, "genai_image", settings.genai_image_daily_cap)
        generated = await genai.search(scene.visual_hint, project["format"], per_page=1)
        if not generated:
            raise AppError("Image generation produced nothing", hint="Try again in a moment")
        guards.increment_usage(conn, "genai_image")
        chosen, engine_used, alternates = generated[0], "genai", []
    else:
        if not payload.source_id:
            raise AppError("Pick a candidate or request generate_new", hint="source_id or generate_new is required")
        alternates_meta = meta.get("alternates", [])
        match = next((a for a in alternates_meta if a["source_id"] == payload.source_id), None)
        if match is None:
            raise NotFoundError(f"Candidate {payload.source_id} not found among this scene's alternates")
        chosen = ImageCandidate(**match)
        engine_used = match["source"]
        # The picked alternate drops out of the new alternates list; the
        # previous winner joins it so it isn't lost.
        previous_winner = ImageCandidate(
            source=meta.get("source", engine_used), source_id=meta.get("source_id", ""),
            width=meta.get("width") or 0, height=meta.get("height") or 0,
            url=meta.get("url"), photographer=meta.get("photographer"), photographer_url=meta.get("photographer_url"),
        )
        alternates = [ImageCandidate(**a) for a in alternates_meta if a["source_id"] != payload.source_id]
        alternates.append(previous_winner)

    await image_service.download_candidate(chosen, out_path)
    new_meta = image_service._credit_meta(chosen, engine_used, alternates)
    mode_b._upsert_media_asset(conn, project_id, "image", scene_id, out_path, new_meta)
    # A swapped image invalidates any generated-footage clip made from the
    # old image - the scene falls back to Ken Burns honestly (task-20a).
    mode_b.delete_scene_clip(conn, project_id, scene_id)

    job_id = job_queue.enqueue(
        conn, user_id, project_id, "rerender_scene",
        {"project_id": project_id, "scene_id": scene_id},
    )
    conn.execute("UPDATE projects SET status = 'generating' WHERE id = ?", (project_id,))
    conn.commit()
    job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(conn, job_row)


@router.post("/{project_id}/scenes/{scene_id}/rerender", response_model=JobOut, status_code=201)
def rerender_scene_endpoint(
    project_id: str,
    scene_id: int,
    payload: SceneRerenderRequest,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> JobOut:
    project = get_owned_project(conn, project_id, user_id)
    _get_scene_image_row(conn, project, scene_id)  # 404s honestly if this isn't a rendered Mode B scene

    job_id = job_queue.enqueue(
        conn, user_id, project_id, "rerender_scene",
        {
            "project_id": project_id, "scene_id": scene_id,
            "retts": True, "resource_image": True,
            "voice": payload.voice,
        },
    )
    conn.execute("UPDATE projects SET status = 'generating' WHERE id = ?", (project_id,))
    conn.commit()
    job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(conn, job_row)


@router.post("/{project_id}/rerender", response_model=RerenderOtherModeOut, status_code=201)
def rerender_other_mode(
    project_id: str,
    payload: RerenderOtherModeRequest,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> RerenderOtherModeOut:
    """Clones the accepted script into a NEW sibling project and renders
    it in the other mode - specs/01-requirements/01-core-flow-and-modes.md:
    "the same accepted script can be re-rendered in the other mode with
    one click"; kept as a separate project (not overwriting this one's
    `mode`/`output_path`) so "produces second output without touching the
    first" holds literally, and reuses the existing render_mode_a/
    render_mode_b pipelines unchanged - no new pipeline code needed for
    this tool.
    """
    project = get_owned_project(conn, project_id, user_id)
    if project["accepted_version_id"] is None:
        raise AppError("Script must be accepted first", hint="Accept the script before re-rendering")
    if project["mode"] is None:
        raise AppError("This project hasn't been rendered yet", hint="Generate a video first")

    target_mode = "b" if project["mode"] == "a" else "a"
    version = conn.execute(
        "SELECT * FROM script_versions WHERE id = ?", (project["accepted_version_id"],)
    ).fetchone()

    mode_label = "Avatar" if target_mode == "a" else "Image Video"
    new_project_id = new_id()
    conn.execute(
        "INSERT INTO projects (id, user_id, title, description, language, duration_s, format, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted')",
        (
            new_project_id, user_id, f"{project['title'] or 'Untitled'} ({mode_label})",
            project["description"], project["language"], project["duration_s"], project["format"],
        ),
    )
    new_version_id = new_id()
    conn.execute(
        "INSERT INTO script_versions (id, project_id, n, scenes_json, origin) VALUES (?, ?, 1, ?, 'cloned')",
        (new_version_id, new_project_id, version["scenes_json"]),
    )
    conn.execute(
        "UPDATE projects SET accepted_version_id = ? WHERE id = ?", (new_version_id, new_project_id)
    )
    conn.commit()

    if target_mode == "a":
        avatar_id = payload.avatar_id
        if not avatar_id:
            fallback = conn.execute(
                "SELECT id FROM avatars WHERE user_id = ? AND approved = 1 ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            avatar_id = fallback["id"] if fallback else None
        if not avatar_id:
            raise AppError("An avatar is required for Mode A", hint="Create and approve an avatar first")
        avatar = conn.execute(
            "SELECT * FROM avatars WHERE id = ? AND user_id = ?", (avatar_id, user_id)
        ).fetchone()
        if avatar is None:
            raise NotFoundError(f"Avatar {avatar_id} not found")
        if not avatar["approved"]:
            raise AppError("This avatar hasn't been approved yet", hint="Approve the portrait first")

        job_id = job_queue.enqueue(
            conn, user_id, new_project_id, "render_mode_a",
            {"project_id": new_project_id, "avatar_id": avatar_id, "subtitles": True, "subtitle_style": "phrase"},
        )
        conn.execute("UPDATE projects SET status = 'generating', mode = 'a' WHERE id = ?", (new_project_id,))
    else:
        job_id = job_queue.enqueue(
            conn, user_id, new_project_id, "render_mode_b",
            {"project_id": new_project_id, "subtitle_style": "phrase"},
        )
        conn.execute("UPDATE projects SET status = 'generating', mode = 'b' WHERE id = ?", (new_project_id,))

    conn.commit()
    job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return RerenderOtherModeOut(project_id=new_project_id, job=_row_to_job(conn, job_row))
