"""Global provider guards — specs/04-tasks/task-15-quotas-fairness.md.

specs/01-requirements/10-hosting-accounts-quotas.md (locked): "global
guards only... honest degradation near caps" - not per-user credits
(explicitly dropped at this product's 1-2 user scale: "~750 LLM calls and
~250 images each" per day are effectively personal anyway). These caps are
safety rails set comfortably above that, not rationing.

Reuses the `usage` table (date, counter, n) already established by
api/script.py's own per-call counters (task-02) and task-11's GPU-seconds
ledger (app/quota/gpu_budget.py) - same shape, same table.
"""
import sqlite3

from app.core.time_utils import pt_today
from app.engines.script_llm import QuotaExhaustedError

DEFAULT_CAPS = {
    "gemini_text": 700,
    "genai_image": 200,
}


def increment_usage(conn: sqlite3.Connection, counter: str, n: int = 1) -> None:
    conn.execute(
        "INSERT INTO usage (date, counter, n) VALUES (?, ?, ?) "
        "ON CONFLICT(date, counter) DO UPDATE SET n = n + excluded.n",
        (pt_today(), counter, n),
    )
    conn.commit()


def usage_today(conn: sqlite3.Connection, counter: str) -> int:
    row = conn.execute(
        "SELECT n FROM usage WHERE date = ? AND counter = ?", (pt_today(), counter)
    ).fetchone()
    return row["n"] if row else 0


def guard(conn: sqlite3.Connection, counter: str, cap: int) -> None:
    """Raises QuotaExhaustedError if `counter`'s usage today is already at
    or past `cap`. Call this BEFORE spending the call it guards, so the cap
    can never be blown past (specs/04-tasks/task-15's own Acceptance:
    "Provider caps can never be blown past (server-enforced)")."""
    if usage_today(conn, counter) >= cap:
        raise QuotaExhaustedError()
