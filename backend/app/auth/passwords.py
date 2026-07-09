"""Argon2 password hashing — specs/04-tasks/task-14-auth-accounts.md.

Uses argon2-cffi directly rather than depending on the `fastapi-users`
library: fastapi-users' user-storage layer is built around an async ORM
adapter (SQLAlchemy/Beanie), which doesn't fit this project's raw-sqlite3
architecture (every other table in this codebase is plain SQL, no ORM) -
writing a correct custom async adapter on top of synchronous sqlite3 would
be a bigger, riskier lift than the two endpoints + one dependency this
actually needs. See task-14's Completion notes for the full reasoning.
"""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
