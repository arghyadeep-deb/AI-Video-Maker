"""GPU-seconds ledger for the ZeroGPU overflow tier — specs/04-tasks/task-11-talking-head.md.

specs/01-requirements/10-hosting-accounts-quotas.md (locked, simplified)
supersedes task-11's own older per-user "GPU slot credit" framing: quotas
are global safety-rail guards, not per-user rationing, at this product's
1-2 user scale. This tracks a single global daily ZeroGPU-seconds counter
in the existing `usage` table (date, counter, n) - same pattern
`_increment_usage` already uses for Gemini calls in api/script.py.

specs/02-research/08-free-hosting.md: free ZeroGPU accounts get roughly
300s programmatic per day. This ledger is our own preemptive estimate, not
the actual HF-side enforcement - HF enforces its own limit regardless.
"""
import sqlite3

from app.core.time_utils import pt_today

COUNTER = "zerogpu_seconds"


def seconds_used_today(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT n FROM usage WHERE date = ? AND counter = ?", (pt_today(), COUNTER)
    ).fetchone()
    return float(row["n"]) if row else 0.0


def has_budget(conn: sqlite3.Connection, daily_limit_seconds: float, estimate_seconds: float) -> bool:
    return seconds_used_today(conn) + estimate_seconds <= daily_limit_seconds


def record_usage(conn: sqlite3.Connection, seconds: float) -> None:
    conn.execute(
        "INSERT INTO usage (date, counter, n) VALUES (?, ?, ?) "
        "ON CONFLICT(date, counter) DO UPDATE SET n = n + excluded.n",
        (pt_today(), COUNTER, round(seconds)),
    )
    conn.commit()


def refund_usage(conn: sqlite3.Connection, seconds: float) -> None:
    """Refund on a ZeroGPU failure that falls back to Wav2Lip -
    specs/04-tasks/task-11-talking-head.md's Implementation notes:
    "on ZeroGPU quota error -> fall back to Wav2Lip and refund the slot".
    """
    conn.execute(
        "UPDATE usage SET n = MAX(0, n - ?) WHERE date = ? AND counter = ?",
        (round(seconds), pt_today(), COUNTER),
    )
    conn.commit()
