"""specs/03-design/09-api-endpoints.md — Projects."""
import shutil
import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.deps import get_current_user_id, get_db
from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.models.project import ProjectCreate, ProjectOut, ProjectSummary
from app.pipelines.common import project_dir
from app.services.project_repo import row_to_project
from app.services.script_repo import get_latest_version_row

router = APIRouter()


def get_owned_project(
    conn: sqlite3.Connection, project_id: str, user_id: str
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Project {project_id} not found")
    return row


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> ProjectOut:
    project_id = new_id()
    conn.execute(
        "INSERT INTO projects (id, user_id, description, language, duration_s, format, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'drafting')",
        (
            project_id,
            user_id,
            payload.description,
            payload.language,
            payload.duration_s,
            payload.format,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return row_to_project(row)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> ProjectOut:
    row = get_owned_project(conn, project_id, user_id)
    latest_version = get_latest_version_row(conn, project_id)
    return row_to_project(row, latest_version)


@router.get("", response_model=list[ProjectSummary])
def list_projects(
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[ProjectSummary]:
    settings = get_settings()
    # created_at alone ties for rows inserted in the same millisecond (its
    # precision) - id (UUIDv7, time-sortable) as a secondary key keeps
    # "newest first" honest even then.
    rows = conn.execute(
        "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC, id DESC", (user_id,)
    ).fetchall()

    summaries = []
    for row in rows:
        thumb_path = project_dir(settings.media_root, user_id, row["id"]) / "thumbnail.jpg"
        active_job = conn.execute(
            "SELECT id FROM jobs WHERE project_id = ? AND status IN ('queued', 'running') "
            "ORDER BY created_at DESC LIMIT 1",
            (row["id"],),
        ).fetchone()

        display_status = row["status"]
        if display_status == "generating" and active_job is None:
            # A render job's failure/cancellation never rewrites
            # projects.status (the worker is pipeline-agnostic and has no
            # notion of "project"), so without this a failed render would
            # leave the project stuck showing "generating" forever with
            # nothing left to poll. Derive the honest display status from
            # the most recent job instead, without touching the DB row.
            last_job = conn.execute(
                "SELECT status FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            if last_job is not None and last_job["status"] in ("failed", "cancelled"):
                display_status = last_job["status"]

        summaries.append(
            ProjectSummary(
                id=row["id"],
                title=row["title"],
                language=row["language"],
                format=row["format"],
                duration_s=row["duration_s"],
                mode=row["mode"],
                status=display_status,
                has_thumbnail=thumb_path.exists(),
                active_job_id=active_job["id"] if active_job else None,
                created_at=row["created_at"],
            )
        )
    return summaries


@router.get("/{project_id}/thumbnail")
def get_project_thumbnail(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    get_owned_project(conn, project_id, user_id)
    settings = get_settings()
    thumb_path = project_dir(settings.media_root, user_id, project_id) / "thumbnail.jpg"
    if not thumb_path.exists():
        raise NotFoundError("No thumbnail yet for this project")
    return FileResponse(thumb_path)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    get_owned_project(conn, project_id, user_id)
    settings = get_settings()

    # projects.accepted_version_id references script_versions - null it out
    # before deleting versions, or the FK constraint (PRAGMA foreign_keys is
    # ON for this connection) rejects the delete.
    conn.execute("UPDATE projects SET accepted_version_id = NULL WHERE id = ?", (project_id,))
    conn.execute("DELETE FROM media_assets WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM jobs WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM script_versions WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()

    shutil.rmtree(project_dir(settings.media_root, user_id, project_id), ignore_errors=True)
