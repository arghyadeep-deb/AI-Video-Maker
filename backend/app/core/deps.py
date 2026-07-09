"""FastAPI dependencies shared by every route.

`get_current_user_id` was a task-02-era placeholder that pinned every
request to one seeded local user, so `user_id` FK/scoping discipline
(specs/03-design/08-data-model.md) was exercised from task-02 onward
instead of being bolted on later. Task-14 replaces its body with real
JWT-cookie session lookup - every existing route's `Depends(get_current_user_id)`
call site is unchanged; only this function's implementation changed.
"""
import sqlite3
from collections.abc import Generator

from fastapi import Depends, Request

from app.auth.tokens import TokenError, decode_access_token
from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.db.connection import get_connection


def get_db() -> Generator[sqlite3.Connection, None, None]:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user_id(
    request: Request, conn: sqlite3.Connection = Depends(get_db)
) -> str:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise UnauthorizedError("Not authenticated")
    try:
        user_id = decode_access_token(token)
    except TokenError:
        raise UnauthorizedError("Session expired or invalid")

    row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise UnauthorizedError("Account no longer exists")
    return user_id


def require_admin(
    user_id: str = Depends(get_current_user_id), conn: sqlite3.Connection = Depends(get_db)
) -> str:
    """Gates the admin-only import-render escape hatch (task-11) even ahead
    of real auth (task-14) - checks `users.role`, which the schema already
    carries. The dev-mode seeded user defaults to role='user'; tests that
    need the authorized path flip it explicitly.
    """
    row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or row["role"] != "admin":
        raise ForbiddenError("Admin access required")
    return user_id
