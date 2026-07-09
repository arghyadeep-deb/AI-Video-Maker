"""Script contract — specs/01-requirements/02-script-generation.md,
specs/03-design/08-data-model.md (`scenes_json`)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Scene(BaseModel):
    id: int
    text: str
    visual_hint: str
    visual_hint_stale: bool = False


class ScriptContract(BaseModel):
    """The LLM's raw structured-output shape (has a title; not persisted as-is)."""

    title: str
    language: Literal["hi", "en"]
    scenes: list[Scene] = Field(min_length=1)


class ScriptVersionOut(BaseModel):
    """A persisted `script_versions` row (scenes only — title lives on the project)."""

    id: str
    project_id: str
    n: int
    scenes: list[Scene]
    origin: Literal["generated", "improved", "edited", "cloned"]
    created_at: str


class ScriptVersionSummary(BaseModel):
    """Lightweight row for the version-history dropdown (no scenes payload)."""

    id: str
    n: int
    origin: Literal["generated", "improved", "edited", "cloned"]
    created_at: str


class SceneEdit(BaseModel):
    text: str


class ImproveRequest(BaseModel):
    """specs/03-design/03-review-loop-design.md. `start`/`end` are Unicode
    codepoint offsets into the scene's `text` (not UTF-16 code units) —
    the frontend converts DOM selection offsets before sending.
    """

    version_id: str
    scene_id: int
    start: int
    end: int
    instruction: Optional[str] = None


class ImproveProposal(BaseModel):
    """Not persisted — the frontend shows this as a keep/revert diff."""

    scene_id: int
    old_span: str
    new_span: str
    proposed_scene_text: str


class ApplyRequest(BaseModel):
    scene_id: int
    proposed_scene_text: str
