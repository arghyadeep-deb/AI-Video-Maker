"""SQLite-backed job queue — specs/03-design/07-job-queue-and-progress.md.

Fairness: the worker claims the oldest queued job of the
least-recently-served user (round-robin across users), not global FIFO —
one user queueing many jobs can't starve others. With one user this is
indistinguishable from FIFO.
"""
import json
import sqlite3
from pathlib import Path

from app.core.ids import new_id
from app.core.time_utils import iso_now
from app.db.connection import get_connection


def enqueue(
    conn: sqlite3.Connection,
    user_id: str,
    project_id: str | None,
    job_type: str,
    payload: dict,
) -> str:
    job_id = new_id()
    conn.execute(
        "INSERT INTO jobs (id, user_id, project_id, type, status, stage, progress, payload_json) "
        "VALUES (?, ?, ?, ?, 'queued', NULL, 0, ?)",
        (job_id, user_id, project_id, job_type, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    return job_id


def _last_served_at(conn: sqlite3.Connection, user_id: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(finished_at) AS t FROM jobs WHERE user_id = ? AND finished_at IS NOT NULL",
        (user_id,),
    ).fetchone()
    return row["t"]


def claim_next_job(conn: sqlite3.Connection) -> sqlite3.Row | None:
    queued = conn.execute(
        "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC"
    ).fetchall()
    if not queued:
        return None

    users_in_arrival_order: list[str] = []
    seen: set[str] = set()
    for job in queued:
        if job["user_id"] not in seen:
            seen.add(job["user_id"])
            users_in_arrival_order.append(job["user_id"])

    def sort_key(user_id: str):
        last_served = _last_served_at(conn, user_id)
        return (last_served is not None, last_served)  # never-served (None) sorts first

    next_user = min(users_in_arrival_order, key=sort_key)
    chosen = next(job for job in queued if job["user_id"] == next_user)

    conn.execute(
        "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
        (iso_now(), chosen["id"]),
    )
    conn.commit()
    return conn.execute("SELECT * FROM jobs WHERE id = ?", (chosen["id"],)).fetchone()


def queue_position(conn: sqlite3.Connection, job_id: str) -> int | None:
    """0-indexed position in the queue (0 = claimed next), simulating the
    same fairness ordering claim_next_job itself uses - specs/04-tasks/
    task-15-quotas-fairness.md: "FIFO... queue position computation".
    Returns None if the job isn't currently queued (already claimed,
    finished, or unknown).
    """
    remaining = conn.execute(
        "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC"
    ).fetchall()
    if not any(j["id"] == job_id for j in remaining):
        return None

    remaining = list(remaining)
    position = 0
    while remaining:
        users_in_arrival_order: list[str] = []
        seen: set[str] = set()
        for job in remaining:
            if job["user_id"] not in seen:
                seen.add(job["user_id"])
                users_in_arrival_order.append(job["user_id"])

        def sort_key(user_id: str):
            last_served = _last_served_at(conn, user_id)
            return (last_served is not None, last_served)

        next_user = min(users_in_arrival_order, key=sort_key)
        chosen = next(job for job in remaining if job["user_id"] == next_user)
        if chosen["id"] == job_id:
            return position
        remaining = [j for j in remaining if j["id"] != chosen["id"]]
        position += 1

    return None  # unreachable given the membership check above


def sweep_interrupted_jobs(db_path: Path) -> int:
    """Startup sweep: any job still `running` means the process died mid-job
    (media steps aren't resumable). Marks them honestly failed.
    Credit refund (per the design doc) is a no-op until task-15 exists.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "UPDATE jobs SET status = 'failed', error = 'restart interrupted', finished_at = ? "
            "WHERE status = 'running'",
            (iso_now(),),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
