"""specs/03-design/09-api-endpoints.md — Avatar (Mode A).

`GET /{avatar_id}`, `GET /{avatar_id}/selfie`, and `GET /{avatar_id}/portrait`
aren't in the locked endpoint table, but the frontend approval-gate UI needs
to poll one specific avatar's styling state (the list endpoint only returns
*approved* avatars) and actually render the images (paths are server-local
filesystem paths, not web-servable on their own) — same kind of small,
documented addition as task-03's `GET /script/versions`.
"""
import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.deps import get_current_user_id, get_db
from app.core.errors import AppError, NotFoundError
from app.core.ids import new_id
from app.jobs import queue as job_queue
from app.models.avatar import AvatarOut, AvatarWithJob, RestyleRequest
from app.moderation.consent import require_consent
from app.moderation.persona_guard import check_persona_description
from app.pipelines import avatar_styling  # noqa: F401 - import registers "avatar_styling"
from app.services.face_check import has_frontal_face

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


def _row_to_avatar(row: sqlite3.Row) -> AvatarOut:
    return AvatarOut(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        persona_description=row["persona_description"],
        selfie_path=row["selfie_path"],
        portrait_path=row["portrait_path"],
        approved=bool(row["approved"]),
        consented=bool(row["consented"]),
        created_at=row["created_at"],
    )


def _get_owned_avatar(conn: sqlite3.Connection, avatar_id: str, user_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM avatars WHERE id = ? AND user_id = ?", (avatar_id, user_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Avatar {avatar_id} not found")
    return row


@router.post("", response_model=AvatarWithJob, status_code=201)
async def create_avatar(
    selfie: UploadFile = File(...),
    persona_description: str = Form(...),
    name: str = Form(...),
    consent: bool = Form(...),
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> AvatarWithJob:
    # Consent gate (locked, specs/01-requirements/04-mode-a-avatar.md), the
    # persona/impersonation guard, and the face-presence gate all reject
    # synchronously at upload, before anything is persisted or queued -
    # specs/03-design/04-mode-a-pipeline.md's failure-modes table calls for
    # "reject at upload with a clear message".
    consented_at = require_consent(consent)

    persona_error = check_persona_description(persona_description)
    if persona_error is not None:
        raise AppError(persona_error, hint="Describe a role or style instead")

    if selfie.content_type not in ALLOWED_CONTENT_TYPES:
        raise AppError("Selfie must be a JPEG or PNG image")

    selfie_bytes = await selfie.read()
    if not has_frontal_face(selfie_bytes):
        raise AppError(
            "No face detected in the selfie",
            hint="Upload a single clear, front-facing photo",
        )

    settings = get_settings()
    avatar_id = new_id()
    ext = ".png" if selfie.content_type == "image/png" else ".jpg"
    avatar_dir = settings.media_root / "users" / user_id / "avatars" / avatar_id
    avatar_dir.mkdir(parents=True, exist_ok=True)
    selfie_path = avatar_dir / f"selfie{ext}"
    selfie_path.write_bytes(selfie_bytes)

    conn.execute(
        "INSERT INTO avatars (id, user_id, name, persona_description, selfie_path, consented, consented_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?)",
        (avatar_id, user_id, name, persona_description, str(selfie_path), consented_at),
    )
    job_id = job_queue.enqueue(conn, user_id, None, "avatar_styling", {"avatar_id": avatar_id})
    conn.commit()

    row = conn.execute("SELECT * FROM avatars WHERE id = ?", (avatar_id,)).fetchone()
    return AvatarWithJob(**_row_to_avatar(row).model_dump(), job_id=job_id)


@router.get("", response_model=list[AvatarOut])
def list_approved_avatars(
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[AvatarOut]:
    rows = conn.execute(
        "SELECT * FROM avatars WHERE user_id = ? AND approved = 1 ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return [_row_to_avatar(r) for r in rows]


@router.get("/{avatar_id}", response_model=AvatarOut)
def get_avatar(
    avatar_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> AvatarOut:
    return _row_to_avatar(_get_owned_avatar(conn, avatar_id, user_id))


@router.get("/{avatar_id}/selfie")
def get_avatar_selfie(
    avatar_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    avatar = _get_owned_avatar(conn, avatar_id, user_id)
    if not avatar["selfie_path"]:
        raise NotFoundError("No selfie on file for this avatar")
    return FileResponse(avatar["selfie_path"])


@router.get("/{avatar_id}/portrait")
def get_avatar_portrait(
    avatar_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    avatar = _get_owned_avatar(conn, avatar_id, user_id)
    if not avatar["portrait_path"]:
        raise NotFoundError("No styled portrait yet for this avatar")
    return FileResponse(avatar["portrait_path"])


@router.post("/{avatar_id}/approve", response_model=AvatarOut)
def approve_avatar(
    avatar_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> AvatarOut:
    avatar = _get_owned_avatar(conn, avatar_id, user_id)
    if not avatar["portrait_path"]:
        raise AppError("No styled portrait to approve yet")
    conn.execute("UPDATE avatars SET approved = 1 WHERE id = ?", (avatar_id,))
    conn.commit()
    return _row_to_avatar(conn.execute("SELECT * FROM avatars WHERE id = ?", (avatar_id,)).fetchone())


@router.post("/{avatar_id}/restyle", response_model=AvatarWithJob)
def restyle_avatar(
    avatar_id: str,
    payload: RestyleRequest,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> AvatarWithJob:
    avatar = _get_owned_avatar(conn, avatar_id, user_id)

    persona_error = check_persona_description(payload.persona_description)
    if persona_error is not None:
        raise AppError(persona_error, hint="Describe a role or style instead")

    conn.execute(
        "UPDATE avatars SET persona_description = ?, approved = 0 WHERE id = ?",
        (payload.persona_description, avatar_id),
    )
    job_id = job_queue.enqueue(conn, user_id, None, "avatar_styling", {"avatar_id": avatar_id})
    conn.commit()

    row = conn.execute("SELECT * FROM avatars WHERE id = ?", (avatar_id,)).fetchone()
    return AvatarWithJob(**_row_to_avatar(row).model_dump(), job_id=job_id)


@router.delete("/{avatar_id}/selfie", response_model=AvatarOut)
def delete_avatar_selfie(
    avatar_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> AvatarOut:
    """specs/01-requirements/09-open-decisions.md #9 (default: keep the
    selfie for restyling, but offer a prominent delete button): removes just
    the selfie file, leaving the approved portrait/persona/avatar itself
    intact and still usable for rendering. A later Regenerate/restyle will
    fail cleanly (no selfie left to re-style from) rather than crash."""
    avatar = _get_owned_avatar(conn, avatar_id, user_id)
    if avatar["selfie_path"]:
        Path(avatar["selfie_path"]).unlink(missing_ok=True)
    conn.execute("UPDATE avatars SET selfie_path = NULL WHERE id = ?", (avatar_id,))
    conn.commit()
    return _row_to_avatar(conn.execute("SELECT * FROM avatars WHERE id = ?", (avatar_id,)).fetchone())


@router.delete("/{avatar_id}", status_code=204)
def delete_avatar(
    avatar_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    avatar = _get_owned_avatar(conn, avatar_id, user_id)
    conn.execute("DELETE FROM avatars WHERE id = ?", (avatar_id,))
    conn.commit()

    # Working deletion of likeness artifacts - hard invariant.
    if avatar["selfie_path"]:
        shutil.rmtree(Path(avatar["selfie_path"]).parent, ignore_errors=True)
