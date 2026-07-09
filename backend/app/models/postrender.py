"""specs/04-tasks/task-17-post-render-tools.md — swap image, scene
re-render, mode re-render request/response shapes."""
from typing import Optional

from pydantic import BaseModel

from app.models.job import JobOut


class CandidateOut(BaseModel):
    source: str
    source_id: str
    width: Optional[int] = None
    height: Optional[int] = None
    url: Optional[str] = None
    photographer: Optional[str] = None
    photographer_url: Optional[str] = None


class SceneCandidatesOut(BaseModel):
    current: CandidateOut
    alternates: list[CandidateOut]
    can_generate_new: bool


class SwapImageRequest(BaseModel):
    source_id: Optional[str] = None
    generate_new: bool = False


class SceneRerenderRequest(BaseModel):
    voice: Optional[str] = None


class RerenderOtherModeRequest(BaseModel):
    avatar_id: Optional[str] = None  # only meaningful when the target mode is 'a'


class RerenderOtherModeOut(BaseModel):
    """A NEW sibling project id + its render job - specs/01-requirements/
    01-core-flow-and-modes.md's own test spec: "produces second output
    without touching the first", since a projects row has exactly one
    mode/output_path and can't hold both renders at once."""

    project_id: str
    job: JobOut
