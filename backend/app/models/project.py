from typing import Literal, Optional

from pydantic import BaseModel

from app.models.script import ScriptVersionOut

Language = Literal["hi", "en"]
DurationS = Literal[30, 60, 120, 300]
Format = Literal["9x16", "16x9"]


class ProjectCreate(BaseModel):
    description: str
    language: Language
    duration_s: DurationS
    format: Format


class ProjectOut(BaseModel):
    id: str
    user_id: str
    title: Optional[str] = None
    description: str
    language: str
    duration_s: int
    format: str
    status: str
    mode: Optional[str] = None
    voice: Optional[str] = None
    accepted_version_id: Optional[str] = None
    output_path: Optional[str] = None
    created_at: str
    # Present on GET /api/projects/{id} (specs/03-design/09-api-endpoints.md);
    # absent (None) on the bare row returned by POST /api/projects.
    latest_script_version: Optional[ScriptVersionOut] = None


class ProjectSummary(BaseModel):
    """Lightweight row for the library grid (task-13) - no scenes payload,
    just what a project card needs."""

    id: str
    title: Optional[str] = None
    language: str
    format: str
    duration_s: int
    mode: Optional[str] = None
    status: str
    has_thumbnail: bool
    active_job_id: Optional[str] = None
    created_at: str
