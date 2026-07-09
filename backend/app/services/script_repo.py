"""Shared script_versions row<->model helpers, used by both api/projects.py
(embedding the latest version in project detail) and api/script.py
(generation response) — kept out of either module to avoid a circular
import between the two.
"""
import json
import sqlite3

from app.models.script import Scene, ScriptVersionOut


def row_to_version(row: sqlite3.Row) -> ScriptVersionOut:
    scenes_data = json.loads(row["scenes_json"])
    return ScriptVersionOut(
        id=row["id"],
        project_id=row["project_id"],
        n=row["n"],
        scenes=[Scene.model_validate(s) for s in scenes_data],
        origin=row["origin"],
        created_at=row["created_at"],
    )


def get_latest_version_row(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM script_versions WHERE project_id = ? ORDER BY n DESC LIMIT 1",
        (project_id,),
    ).fetchone()
