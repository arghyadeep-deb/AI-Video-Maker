from typing import Literal, Optional

from pydantic import BaseModel

JobStatus = Literal["queued", "running", "awaiting_user", "done", "failed", "cancelled"]


class JobOut(BaseModel):
    id: str
    type: str
    status: JobStatus
    stage: Optional[str] = None
    stages: list[str]  # full ordered stage-name list for this job's type
    progress: float
    error: Optional[str] = None
    # 0-indexed jobs ahead of this one, "N jobs ahead of you" (task-15) -
    # only meaningful while status == "queued"; None otherwise.
    queue_position: Optional[int] = None
