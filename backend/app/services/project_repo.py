"""Shared projects row<->model helper — used by api/projects.py and
api/script.py (accept/scrap return the project). Kept separate from
script_repo.py to avoid either api module importing the other.
"""
import sqlite3
from typing import Optional

from app.models.project import ProjectOut
from app.services.script_repo import row_to_version


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
