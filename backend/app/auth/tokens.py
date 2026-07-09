"""JWT session tokens carried in an httponly cookie —
specs/04-tasks/task-14-auth-accounts.md.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from app.core.config import get_settings


class TokenError(Exception):
    pass


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> str:
    """Returns the user_id (sub claim). Raises TokenError on any invalid,
    expired, or tampered token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise TokenError("Token missing 'sub' claim")
    return user_id
