"""Likeness-artifact consent — specs/04-tasks/task-19-moderation-consent.md.

A shared version of the rejection-and-stamping logic that was previously
duplicated independently across `app/api/avatars.py` (selfie) and
`app/api/voices.py` (voice sample) - "same rejection shape", per voices.py's
own comment, now actually the same code. Deletion is handled by each
artifact's own existing delete endpoint (selfie/voice-sample), not here -
there's nothing artifact-specific this module needs to know to delete.
"""
from app.core.errors import AppError
from app.core.time_utils import iso_now

CONSENT_REQUIRED_MESSAGE = "This is your own likeness - consent is required before we can use it"


def require_consent(consent: bool) -> str:
    """Raises if consent wasn't given; otherwise returns the timestamp to
    stamp as `consented_at` (also the "logged consent record" itself - the
    row's own `consented`/`consented_at` columns ARE the record, per this
    task's own "logged consent record (timestamp) per avatar/voice
    profile" - no separate audit table is needed at 1-2 users)."""
    if not consent:
        raise AppError(CONSENT_REQUIRED_MESSAGE, hint="Check the consent box to continue")
    return iso_now()
