from typing import Literal, Optional

from pydantic import BaseModel

VoiceProfileKind = Literal["cloned", "designed"]


class VoiceProfileOut(BaseModel):
    id: str
    user_id: str
    kind: VoiceProfileKind
    description: Optional[str] = None
    base_voice: Optional[str] = None
    consented: bool
    created_at: str


class VoiceEnrollRequest(BaseModel):
    """Multipart form fields alongside the uploaded sample - see
    app/api/voices.py's enroll endpoint for the file field itself."""

    consent: bool
    base_voice: Optional[str] = None  # user-override; auto-picked from pitch if omitted


class VoiceDesignRequest(BaseModel):
    """No consent field - a designed persona voice has no real person's
    voice sample behind it (a text description only), so this project's
    "likeness artifacts require logged consent" hard invariant doesn't
    apply the way it does to `enroll`'s real voice sample."""

    description: str
