"""Shared projects row<->model helper — used by api/projects.py and
api/script.py (accept/scrap return the project). Kept separate from
script_repo.py to avoid either api module importing the other.
"""
import sqlite3
from typing import Optional

from app.models.project import ProjectOut
from app.services.script_repo import row_to_version


def effective_status(conn: sqlite3.Connection, project_id: str, raw_status: str) -> str:
    """Derive the true current status for a project whose raw `status` column
    never reverts once it flips to "generating" - a render job's
    failure/cancellation never rewrites projects.status (the worker is
    pipeline-agnostic and has no notion of "project"). Checks the most
    recent job instead, without touching the DB row. Shared by the
    library-list display (api/projects.py) and the re-generate gate
    (api/video.py) - task-13 fixed the former but not the latter, which
    left a project whose render was killed permanently unable to retry."""
    if raw_status != "generating":
        return raw_status
    active_job = conn.execute(
        "SELECT id FROM jobs WHERE project_id = ? AND status IN ('queued', 'running') "
        "ORDER BY created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if active_job is not None:
        return raw_status
    last_job = conn.execute(
        "SELECT status FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if last_job is not None and last_job["status"] in ("failed", "cancelled"):
        return last_job["status"]
    return raw_status


def row_to_project(
    row: sqlite3.Row, latest_version: Optional[sqlite3.Row] = None
) -> ProjectOut:
    return ProjectOut(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        description=row["description"],
        language=row["language"],
        duration_s=row["duration_s"],
        format=row["format"],
        status=row["status"],
        mode=row["mode"],
        voice=row["voice"],
        accepted_version_id=row["accepted_version_id"],
        output_path=row["output_path"],
        created_at=row["created_at"],
        latest_script_version=row_to_version(latest_version) if latest_version else None,
    )
