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
from app.engines.home_worker_styler import HomeWorkerImageStyler
from app.engines.image_styler import ImageStyler, ImageStylerUnavailableError
from app.jobs.gpu_router import GpuTaskFailed, HomeWorkerUnavailable
from app.jobs.registry import AwaitingUser, JobContext, register_pipeline


class AvatarStylingError(Exception):
    pass


def make_image_styler() -> ImageStyler:
    settings = get_settings()
    return ImageStyler(api_key=settings.gemini_api_key, model=settings.avatar_styling_model)


def make_home_worker_styler(cancelled=None) -> HomeWorkerImageStyler:
    """Tier 2 (task-22): tried after Gemini fails, before the raw-selfie
    floor. Always constructed - the engine itself checks worker presence
    per style() call, mirroring make_home_worker_engine's own comment in
    pipelines/mode_a.py."""
    settings = get_settings()
    return HomeWorkerImageStyler(settings.db_path, settings, cancelled=cancelled)


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
            note = "styled via gemini"
        except ImageStylerUnavailableError as exc:
            # Risk R2, triggered for real in July 2026: Google removed image
            # generation from the API's free tier ("limit: 0"). Tier 2
            # (task-22): try the local home-worker styler before giving up
            # on real styling entirely.
            home_styler = make_home_worker_styler(cancelled=ctx.cancelled)
            try:
                portrait_bytes = await home_styler.style(
                    selfie_bytes, mime_type, avatar["persona_description"]
                )
                note = "styled via home worker (gemini unavailable)"
            except (HomeWorkerUnavailable, GpuTaskFailed) as home_exc:
                # The honest floor: offer the RAW selfie as the portrait at
                # the same approval gate - the user decides whether an
                # unstyled avatar is acceptable; nothing renders without
                # their explicit approval either way.
                portrait_bytes = selfie_bytes
                suffix = selfie_path.suffix or ".jpg"
                note = (
                    "styling unavailable - raw selfie offered as portrait "
                    f"(gemini: {str(exc)[:120]}; home worker: {str(home_exc)[:120]})"
                )
        ctx.report(90)

        # One file per attempt, not a fixed overwritten name - the task's
        # own Implementation notes call for "previous portraits kept until
        # approval" so a restyle doesn't destroy the prior attempt.
        job_id = ctx.job_id
        portrait_path = selfie_path.parent / f"portrait_{job_id}{suffix}"
        portrait_path.write_bytes(portrait_bytes)
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
