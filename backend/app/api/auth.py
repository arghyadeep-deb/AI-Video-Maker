"""specs/04-tasks/task-14-auth-accounts.md — login/logout.

No public registration endpoint: accounts are created only via
`backend/scripts/create_user.py` (an owner-run CLI), per the locked
"no open registration, no email verification" decision — open decision
#12 is retired by this.
"""
import sqlite3

from fastapi import APIRouter, Depends, Request, Response

from app.auth.passwords import verify_password
from app.auth.tokens import create_access_token
from app.core.config import get_settings
from app.core.deps import get_db
from app.core.errors import AppError
from app.core.limiter import limiter
from app.models.auth import LoginRequest, UserOut

router = APIRouter()


def session_cookie_attrs(settings) -> dict:
    """Shared set_cookie/delete_cookie attributes - a cross-origin deploy
    (frontend on Vercel, backend elsewhere) needs SameSite=None (which
    requires Secure); same-origin/localhost dev keeps the friendlier Lax.
    Mismatched attributes between set and delete can leave a stale cookie
    the browser never clears, so every cookie touch-point uses this."""
    cross_origin = not settings.frontend_origin.startswith("http://localhost")
    return {"samesite": "none" if cross_origin else "lax", "secure": cross_origin, "path": "/"}


def _row_to_user(row: sqlite3.Row) -> UserOut:
    return UserOut(id=row["id"], email=row["email"], role=row["role"], created_at=row["created_at"])


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    conn: sqlite3.Connection = Depends(get_db),
) -> UserOut:
    row = conn.execute("SELECT * FROM users WHERE email = ?", (payload.email,)).fetchone()
    # Same message for "no such email" and "wrong password" - don't leak
    # which accounts exist.
    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise AppError("Invalid email or password", hint="Check your email and password")

    token = create_access_token(row["id"])
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        max_age=settings.jwt_expire_minutes * 60,
        **session_cookie_attrs(settings),
    )
    return _row_to_user(row)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, **session_cookie_attrs(settings))
