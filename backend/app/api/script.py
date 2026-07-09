"""specs/03-design/09-api-endpoints.md — Script (synchronous, seconds).

task-02: generate/regenerate. task-03: manual edit, version history +
restore, accept, scrap. task-04 (this file's newest scope): AI
improve-selection (improve/apply).
"""
import json
import sqlite3

from fastapi import APIRouter, Depends

from app.api.projects import get_owned_project
from app.core.config import get_settings
from app.core.deps import get_current_user_id, get_db
from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.engines.script_llm import ScriptLLM
from app.models.project import ProjectOut
from app.models.script import (
    ApplyRequest,
    ImproveProposal,
    ImproveRequest,
    Scene,
    SceneEdit,
    ScriptVersionOut,
    ScriptVersionSummary,
)
from app.quota import guards
from app.services import improve_service, script_service
from app.services.project_repo import row_to_project
from app.services.script_repo import get_latest_version_row, row_to_version

router = APIRouter()


def get_script_llm() -> ScriptLLM:
    settings = get_settings()
    return ScriptLLM(api_key=settings.gemini_api_keys, model=settings.script_llm_model)


def _fetch_latest_version_row(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
    row = get_latest_version_row(conn, project_id)
    if row is None:
        raise NotFoundError(f"Project {project_id} has no script yet")
    return row


def _insert_new_version(
    conn: sqlite3.Connection, project_id: str, scenes: list[Scene], origin: str
) -> sqlite3.Row:
    next_n = conn.execute(
        "SELECT COALESCE(MAX(n), 0) + 1 FROM script_versions WHERE project_id = ?",
        (project_id,),
    ).fetchone()[0]
    version_id = new_id()
    scenes_json = json.dumps([s.model_dump() for s in scenes], ensure_ascii=False)
    conn.execute(
        "INSERT INTO script_versions (id, project_id, n, scenes_json, origin) "
        "VALUES (?, ?, ?, ?, ?)",
        (version_id, project_id, next_n, scenes_json, origin),
    )
    script_service.prune_old_versions(conn, project_id)
    conn.commit()
    return conn.execute(
        "SELECT * FROM script_versions WHERE id = ?", (version_id,)
    ).fetchone()


@router.post("/{project_id}/script", response_model=ScriptVersionOut, status_code=201)
def generate_script(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
    llm: ScriptLLM = Depends(get_script_llm),
) -> ScriptVersionOut:
    project = get_owned_project(conn, project_id, user_id)
    settings = get_settings()
    # New scripts stop earlier than the hard cap - in-flight improve-work
    # on already-started scripts stays "sacred" per the degradation table.
    guards.guard(
        conn, "gemini_text", settings.gemini_text_daily_cap - settings.gemini_text_new_script_reserve
    )

    contract = script_service.generate_script(
        llm, project["description"], project["language"], project["duration_s"]
    )
    guards.increment_usage(conn, "gemini_text")

    row = _insert_new_version(conn, project_id, contract.scenes, origin="generated")
    conn.execute(
        "UPDATE projects SET status = 'script_ready', title = COALESCE(title, ?) WHERE id = ?",
        (contract.title, project_id),
    )
    conn.commit()

    return row_to_version(row)


@router.get("/{project_id}/script/versions", response_model=list[ScriptVersionSummary])
def list_versions(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[ScriptVersionSummary]:
    get_owned_project(conn, project_id, user_id)
    rows = conn.execute(
        "SELECT id, n, origin, created_at FROM script_versions "
        "WHERE project_id = ? ORDER BY n DESC",
        (project_id,),
    ).fetchall()
    return [
        ScriptVersionSummary(id=r["id"], n=r["n"], origin=r["origin"], created_at=r["created_at"])
        for r in rows
    ]


@router.put("/{project_id}/script/scene/{scene_id}", response_model=ScriptVersionOut)
def edit_scene(
    project_id: str,
    scene_id: int,
    payload: SceneEdit,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> ScriptVersionOut:
    get_owned_project(conn, project_id, user_id)
    latest = _fetch_latest_version_row(conn, project_id)
    scenes = [Scene.model_validate(s) for s in json.loads(latest["scenes_json"])]
    updated_scenes = script_service.apply_manual_edit(scenes, scene_id, payload.text)
    row = _insert_new_version(conn, project_id, updated_scenes, origin="edited")
    return row_to_version(row)


@router.post("/{project_id}/script/restore/{version_id}", response_model=ScriptVersionOut)
def restore_version(
    project_id: str,
    version_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> ScriptVersionOut:
    get_owned_project(conn, project_id, user_id)
    target = conn.execute(
        "SELECT * FROM script_versions WHERE id = ? AND project_id = ?",
        (version_id, project_id),
    ).fetchone()
    if target is None:
        raise NotFoundError(f"Version {version_id} not found")
    scenes = [Scene.model_validate(s) for s in json.loads(target["scenes_json"])]
    # Restoring is a form of manual reversion - closest existing origin value.
    row = _insert_new_version(conn, project_id, scenes, origin="edited")
    return row_to_version(row)


@router.post("/{project_id}/script/improve", response_model=ImproveProposal)
def improve_selection(
    project_id: str,
    payload: ImproveRequest,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
    llm: ScriptLLM = Depends(get_script_llm),
) -> ImproveProposal:
    project = get_owned_project(conn, project_id, user_id)
    settings = get_settings()
    # In-flight improve-work uses the full cap, not the reserved-headroom
    # threshold new scripts stop at - "in-flight work is sacred".
    guards.guard(conn, "gemini_text", settings.gemini_text_daily_cap)

    version_row = conn.execute(
        "SELECT * FROM script_versions WHERE id = ? AND project_id = ?",
        (payload.version_id, project_id),
    ).fetchone()
    if version_row is None:
        raise NotFoundError(f"Version {payload.version_id} not found")
    scenes = [Scene.model_validate(s) for s in json.loads(version_row["scenes_json"])]

    old_span, new_span, proposed_scene_text = improve_service.make_proposal(
        llm,
        scenes,
        payload.scene_id,
        payload.start,
        payload.end,
        payload.instruction,
        project["language"],
    )
    guards.increment_usage(conn, "gemini_text")
    conn.commit()

    return ImproveProposal(
        scene_id=payload.scene_id,
        old_span=old_span,
        new_span=new_span,
        proposed_scene_text=proposed_scene_text,
    )


@router.post("/{project_id}/script/apply", response_model=ScriptVersionOut)
def apply_improvement(
    project_id: str,
    payload: ApplyRequest,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> ScriptVersionOut:
    get_owned_project(conn, project_id, user_id)
    latest = _fetch_latest_version_row(conn, project_id)
    scenes = [Scene.model_validate(s) for s in json.loads(latest["scenes_json"])]
    # Same splice-one-scene mechanics as manual edit; only the origin differs.
    updated_scenes = script_service.apply_manual_edit(
        scenes, payload.scene_id, payload.proposed_scene_text
    )
    row = _insert_new_version(conn, project_id, updated_scenes, origin="improved")
    return row_to_version(row)


@router.post("/{project_id}/script/accept", response_model=ProjectOut)
def accept_script(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> ProjectOut:
    get_owned_project(conn, project_id, user_id)
    latest = _fetch_latest_version_row(conn, project_id)
    conn.execute(
        "UPDATE projects SET status = 'accepted', accepted_version_id = ? WHERE id = ?",
        (latest["id"], project_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return row_to_project(row, latest)


@router.delete("/{project_id}/script", response_model=ProjectOut)
def scrap_script(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> ProjectOut:
    get_owned_project(conn, project_id, user_id)
    conn.execute(
        "UPDATE projects SET status = 'drafting', accepted_version_id = NULL WHERE id = ?",
        (project_id,),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return row_to_project(row)
