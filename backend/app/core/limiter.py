"""Shared slowapi Limiter instance — specs/04-tasks/task-14-auth-accounts.md:
"basic rate-limit on the login endpoint... it's still on the public
internet." A single module-level instance so both app.main (which wires it
into the FastAPI app) and app.api.auth (which decorates the login route)
share the same limiter.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
