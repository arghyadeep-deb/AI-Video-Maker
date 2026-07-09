"""Shared jobs row<->model helper — used by api/jobs.py and api/video.py
(both previously carried their own duplicate copy)."""
import sqlite3

from app.jobs import queue as job_queue
from app.jobs import registry
from app.models.job import JobOut


def row_to_job(conn: sqlite3.Connection, row: sqlite3.Row) -> JobOut:
    return JobOut(
        id=row["id"],
        type=row["type"],
        status=row["status"],
        stage=row["stage"],
        stages=registry.stage_names(row["type"]) if registry.is_registered(row["type"]) else [],
        progress=row["progress"],
        error=row["error"],
        queue_position=job_queue.queue_position(conn, row["id"]) if row["status"] == "queued" else None,
    )
