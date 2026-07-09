"""specs/04-tasks/task-15-quotas-fairness.md — Admin `/api/admin/usage`:
"today's counters per provider". Gated by require_admin (task-11's
addition ahead of task-14's real auth, now backed by real roles)."""
import sqlite3

from fastapi import APIRouter, Depends

from app.core.deps import get_db, require_admin
from app.core.time_utils import pt_today

router = APIRouter()

COUNTERS = ("gemini_text", "genai_image", "zerogpu_seconds")


@router.get("/usage")
def usage_today(
    _admin_user_id: str = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    today = pt_today()
    rows = conn.execute("SELECT counter, n FROM usage WHERE date = ?", (today,)).fetchall()
    by_counter = {row["counter"]: row["n"] for row in rows}
    return {"date": today, "counters": {counter: by_counter.get(counter, 0) for counter in COUNTERS}}
