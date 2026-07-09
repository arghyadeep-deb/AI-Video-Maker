from typing import Optional

from pydantic import BaseModel


class AvatarOut(BaseModel):
    id: str
    user_id: str
    name: Optional[str] = None
    persona_description: Optional[str] = None
    selfie_path: Optional[str] = None
    portrait_path: Optional[str] = None
    approved: bool
    consented: bool
    created_at: str


class AvatarWithJob(AvatarOut):
    job_id: str


class RestyleRequest(BaseModel):
    persona_description: str
