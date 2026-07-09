"""specs/03-design/09-api-endpoints.md — Jobs.

`POST /debug/noop` is not part of the locked API surface — it exists so
this task (and future UI dev) has something to kick off and watch without
a real pipeline (avatar_styling/render_mode_a/b) existing yet. Revisit
whether to keep it once real pipelines land (task-09 onward).
"""
import json
import sqlite3

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.core.config import get_settings
from app.core.deps import get_current_user_id, get_db, require_admin
from app.core.errors import AppError, NotFoundError
from app.core.time_utils import iso_now
from app.jobs import queue as job_queue
from app.jobs.pipelines import noop  # noqa: F401 - import registers "noop_render"
from app.jobs.worker import Worker
from app.models.job import JobOut
from app.services.ffmpeg.probe import probe_duration_s
from app.services.job_repo import row_to_job as _row_to_job

router = APIRouter()

IMPORT_DURATION_TOLERANCE_S = 2.0


def get_worker(request: Request) -> Worker:
    return request.app.state.worker


@router.post("/debug/noop", response_model=JobOut, status_code=201)
def create_debug_noop_job(
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> JobOut:
    job_id = job_queue.enqueue(conn, user_id, None, "noop_render", {})
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(conn, row)


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> JobOut:
    row = conn.execute(
        "SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Job {job_id} not found")
    return _row_to_job(conn, row)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
    worker: Worker = Depends(get_worker),
) -> JobOut:
    row = conn.execute(
        "SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Job {job_id} not found")
    worker.request_cancel(job_id)
    return _row_to_job(conn, row)


@router.post("/{job_id}/import-render", response_model=JobOut)
async def import_render(
    job_id: str,
    video: UploadFile = File(...),
    admin_user_id: str = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
) -> JobOut:
    """Admin escape hatch for stuck jobs — specs/04-tasks/task-11-talking-head.md
    ("notebooks/render_avatar.ipynb + POST /jobs/{id}/import-render"). Lets
    the owner manually attach a video rendered out-of-band (e.g. a Colab
    notebook) to a job the normal pipeline couldn't finish. Duration must
    match the job's expected audio duration within ±2s — a bare sanity
    check, not proof the content is actually correct.
    """
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Job {job_id} not found")

    payload = json.loads(row["payload_json"] or "{}")
    expected_duration_s = payload.get("expected_duration_s")

    settings = get_settings()
    video_bytes = await video.read()
    tmp_dir = settings.media_root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"import_{job_id}.mp4"
    tmp_path.write_bytes(video_bytes)

    if expected_duration_s is not None:
        actual_duration_s = probe_duration_s(tmp_path)
        if actual_duration_s is None or abs(actual_duration_s - expected_duration_s) > IMPORT_DURATION_TOLERANCE_S:
            tmp_path.unlink(missing_ok=True)
            raise AppError(
                f"Uploaded video duration doesn't match this job's expected audio "
                f"duration (expected {expected_duration_s:.1f}s +/- {IMPORT_DURATION_TOLERANCE_S}s, "
                f"got {actual_duration_s if actual_duration_s is not None else 'unreadable'})",
                hint="Re-render or double-check the uploaded file",
            )

    final_dir = settings.media_root / "users" / row["user_id"] / "imports"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_path = final_dir / f"{job_id}.mp4"
    final_path.write_bytes(video_bytes)
    tmp_path.unlink(missing_ok=True)

    conn.execute(
        "UPDATE jobs SET status = 'done', stage = NULL, progress = 100, "
        "result_json = ?, engine_notes = ?, finished_at = ? WHERE id = ?",
        (
            json.dumps({"video_path": str(final_path)}),
            f"colab-manual (admin import by {admin_user_id})",
            iso_now(),
            job_id,
        ),
    )
    conn.commit()
    updated_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(conn, updated_row)
