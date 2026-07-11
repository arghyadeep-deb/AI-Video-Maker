"""avatar_styling pipeline — specs/03-design/04-mode-a-pipeline.md.

selfie -> ImageStyler.style -> portrait saved -> park as `awaiting_user`
(never "done" — a human must approve or regenerate). The face-presence
check happens synchronously at upload time (api/avatars.py), not here —
specs/03-design/04-mode-a-pipeline.md's failure-modes table calls for
"reject at upload with a clear message", not a job that fails later.
"""
from pathlib import Path

from app.core.config import get_settings
from app.db.connection import get_connection
from app.engines.image_styler import ImageStyler, ImageStylerUnavailableError
from app.jobs.registry import AwaitingUser, JobContext, register_pipeline


class AvatarStylingError(Exception):
    pass


def make_image_styler() -> ImageStyler:
    settings = get_settings()
    return ImageStyler(api_key=settings.gemini_api_key, model=settings.avatar_styling_model)


async def stage_style(ctx: JobContext) -> None:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        avatar_id = ctx.payload["avatar_id"]
        avatar = conn.execute("SELECT * FROM avatars WHERE id = ?", (avatar_id,)).fetchone()
        if avatar is None:
            raise AvatarStylingError(f"Avatar {avatar_id} not found")
        if not avatar["selfie_path"]:
            # The selfie can be deleted independently (task-13, open
            # decision #9's delete button) while the avatar/portrait stay
            # usable - but a restyle needs the original selfie, and there's
            # none left to re-style from.
            raise AvatarStylingError(
                f"Avatar {avatar_id} has no selfie on file (it was deleted) - restyling isn't possible"
            )

        selfie_path = Path(avatar["selfie_path"])
        selfie_bytes = selfie_path.read_bytes()
        ctx.report(20)

        styler = make_image_styler()
        mime_type = "image/png" if selfie_path.suffix.lower() == ".png" else "image/jpeg"
        suffix = ".png"
        note = None
        try:
            portrait_bytes = styler.style(selfie_bytes, mime_type, avatar["persona_description"])
        except ImageStylerUnavailableError as exc:
            # Risk R2, triggered for real in July 2026: Google removed image
            # generation from the API's free tier ("limit: 0"). The honest
            # degrade: offer the RAW selfie as the portrait at the same
            # approval gate - the user decides whether an unstyled avatar is
            # acceptable; nothing renders without their explicit approval
            # either way. (The full R2 fallback - local styling on the GPU
            # worker - is tracked in specs/06-risks-and-future/01-risks.md.)
            portrait_bytes = selfie_bytes
            suffix = selfie_path.suffix or ".jpg"
            note = f"styling unavailable - raw selfie offered as portrait ({str(exc)[:200]})"
        ctx.report(90)

        # One file per attempt, not a fixed overwritten name - the task's
        # own Implementation notes call for "previous portraits kept until
        # approval" so a restyle doesn't destroy the prior attempt.
        job_id = ctx.job_id
        portrait_path = selfie_path.parent / f"portrait_{job_id}{suffix}"
        portrait_path.write_bytes(portrait_bytes)
        if note is not None:
            conn.execute("UPDATE jobs SET engine_notes = ? WHERE id = ?", (note, job_id))

        conn.execute(
            "UPDATE avatars SET portrait_path = ? WHERE id = ?", (str(portrait_path), avatar_id)
        )
        conn.commit()
        ctx.report(100)

        # Never "done" - the portrait needs human approval before anything
        # (including a restyle retry) proceeds. specs/01-requirements/04-mode-a-avatar.md.
        raise AwaitingUser()
    finally:
        conn.close()


AVATAR_STYLING_PIPELINE = [("style", stage_style)]
register_pipeline("avatar_styling", AVATAR_STYLING_PIPELINE)
