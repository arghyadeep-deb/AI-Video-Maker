"""specs/04-tasks/task-14-auth-accounts.md — Profile + account deletion.

No credits-view stub here: specs/01-requirements/10-hosting-accounts-quotas.md
(locked, and written to supersede this task's own older framing) drops
per-user credits entirely in favor of global-only guards at this product's
1-2 user scale - a fake credits field with no real enforcement behind it
would be dishonest UI, the same call already made for the library page's
missing credits header at task-13.
"""
import shutil
import sqlite3

from fastapi import APIRouter, Depends, Response

from app.api.auth import session_cookie_attrs
from app.core.config import get_settings
from app.core.deps import get_current_user_id, get_db
from app.models.auth import UserOut

router = APIRouter()


def _row_to_user(row: sqlite3.Row) -> UserOut:
    return UserOut(id=row["id"], email=row["email"], role=row["role"], created_at=row["created_at"])


@router.get("", response_model=UserOut)
def get_me(
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> UserOut:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row)


@router.delete("", status_code=204)
def delete_me(
    response: Response,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    """Complete, irreversible account deletion — specs/04-tasks/task-14-auth-accounts.md
    Acceptance: "DB + filesystem... irreversible." Deletion order matters:
    PRAGMA foreign_keys is ON, and projects.accepted_version_id references
    script_versions - the same ordering trap task-13 hit for a single
    project delete, here for every project this user owns at once.
    """
    settings = get_settings()

    conn.execute("UPDATE projects SET accepted_version_id = NULL WHERE user_id = ?", (user_id,))
    conn.execute(
        "DELETE FROM media_assets WHERE project_id IN (SELECT id FROM projects WHERE user_id = ?)",
        (user_id,),
    )
    conn.execute("DELETE FROM jobs WHERE user_id = ?", (user_id,))
    conn.execute(
        "DELETE FROM script_versions WHERE project_id IN (SELECT id FROM projects WHERE user_id = ?)",
        (user_id,),
    )
    conn.execute("DELETE FROM projects WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM avatars WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM voice_profiles WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM credits WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()

    shutil.rmtree(settings.media_root / "users" / user_id, ignore_errors=True)

    response.delete_cookie(settings.session_cookie_name, **session_cookie_attrs(settings))
