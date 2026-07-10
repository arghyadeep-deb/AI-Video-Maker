"""Home GPU worker routing — specs/03-design/11-gpu-worker.md, task-20a.

Two queues, two workers:
  * `jobs` + jobs/worker.py — user-visible pipeline runs, executed on the VM.
  * `gpu_tasks` (this module) — individual GPU sub-steps of those pipelines
    (a SadTalker render, one scene's generated-footage clip), pulled by the
    owner's PC over outbound HTTPS. A pipeline stage submits a task, then
    awaits it here while the remote agent leases/heartbeats/completes it.

Three-tier consequence ("worker -> ZeroGPU -> CPU"): engines built on this
module raise HomeWorkerUnavailable/GpuTaskFailed instead of crashing the
pipeline; callers catch and fall to the next tier with an honest note.

Lease rule (locked in the design doc): heartbeat every 10 s, a task missing
3 heartbeats returns to the queue — a PC put to sleep mid-render is a normal
event, not an error. Partial results are discarded; the stage restarts.
"""
import asyncio
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from app.core.config import Settings
from app.core.ids import new_id
from app.core.time_utils import iso_now
from app.db.connection import get_connection

GpuTaskKind = str  # 'sadtalker' | 'voxcpm' | 'musetalk' | 'scene_gen'

WAIT_POLL_INTERVAL_S = 0.5


class GpuTaskFailed(Exception):
    """The task itself failed (engine crash on the PC, or exhausted lease
    attempts). Callers fall back to the next tier."""


class HomeWorkerUnavailable(Exception):
    """No online worker advertises the needed capability right now."""


def _iso_ago(seconds: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


# --- worker presence -------------------------------------------------------

def record_worker_poll(
    conn: sqlite3.Connection, capabilities: list[str], vram_free_mb: Optional[int]
) -> None:
    conn.execute(
        "INSERT INTO worker_status (id, last_poll_at, capabilities_json, vram_free_mb) "
        "VALUES (1, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET last_poll_at = excluded.last_poll_at, "
        "capabilities_json = excluded.capabilities_json, vram_free_mb = excluded.vram_free_mb",
        (iso_now(), json.dumps(capabilities), vram_free_mb),
    )
    conn.commit()


def worker_online(conn: sqlite3.Connection, settings: Settings) -> bool:
    row = conn.execute("SELECT last_poll_at FROM worker_status WHERE id = 1").fetchone()
    if row is None:
        return False
    return row["last_poll_at"] >= _iso_ago(settings.worker_online_window_s)


def worker_capabilities(conn: sqlite3.Connection, settings: Settings) -> set[str]:
    """Empty set when offline — capability implies presence."""
    if not worker_online(conn, settings):
        return set()
    row = conn.execute("SELECT capabilities_json FROM worker_status WHERE id = 1").fetchone()
    return set(json.loads(row["capabilities_json"]))


# --- task lifecycle --------------------------------------------------------

def submit_task(
    conn: sqlite3.Connection,
    kind: GpuTaskKind,
    payload: dict,
    input_files: list[dict],
) -> str:
    """input_files: [{"name": …, "path": …}] — VM-local files the agent will
    download through one-time signed URLs minted at lease time."""
    task_id = new_id()
    conn.execute(
        "INSERT INTO gpu_tasks (id, kind, status, payload_json, input_files_json) "
        "VALUES (?, ?, 'queued', ?, ?)",
        (task_id, kind, json.dumps(payload, ensure_ascii=False), json.dumps(input_files)),
    )
    conn.commit()
    return task_id


def sweep_expired_leases(conn: sqlite3.Connection, settings: Settings) -> int:
    """Leased tasks whose heartbeat went stale return to the queue (attempts
    permitting) or fail for good. Called from the poll endpoint AND from
    wait_for_task's loop — when the agent vanishes nobody polls, so the
    waiting pipeline must run the sweep itself or it would hang until its
    own timeout instead of failing over promptly."""
    cutoff = _iso_ago(settings.worker_lease_timeout_s)
    expired = conn.execute(
        "SELECT id, attempts FROM gpu_tasks WHERE status = 'leased' AND last_heartbeat_at < ?",
        (cutoff,),
    ).fetchall()
    for row in expired:
        if row["attempts"] < settings.worker_task_max_attempts:
            conn.execute(
                "UPDATE gpu_tasks SET status = 'queued', leased_at = NULL, "
                "last_heartbeat_at = NULL, progress = 0 WHERE id = ?",
                (row["id"],),
            )
        else:
            conn.execute(
                "UPDATE gpu_tasks SET status = 'failed', "
                "error = 'worker lost (lease expired after max attempts)', finished_at = ? "
                "WHERE id = ?",
                (iso_now(), row["id"]),
            )
    if expired:
        conn.commit()
    return len(expired)


def lease_next_task(
    conn: sqlite3.Connection, capabilities: list[str], settings: Settings
) -> sqlite3.Row | None:
    """Oldest queued task the agent can run. FIFO is the locked queueing
    decision (specs/01-requirements/10-hosting-accounts-quotas.md); the
    user-fairness scheduling already happened when the parent `jobs` row was
    claimed, so gpu_tasks need no second fairness pass."""
    sweep_expired_leases(conn, settings)
    if not capabilities:
        return None
    placeholders = ",".join("?" for _ in capabilities)
    row = conn.execute(
        f"SELECT * FROM gpu_tasks WHERE status = 'queued' AND kind IN ({placeholders}) "
        "ORDER BY created_at ASC LIMIT 1",
        capabilities,
    ).fetchone()
    if row is None:
        return None
    now = iso_now()
    conn.execute(
        "UPDATE gpu_tasks SET status = 'leased', leased_at = ?, last_heartbeat_at = ?, "
        "attempts = attempts + 1 WHERE id = ?",
        (now, now, row["id"]),
    )
    conn.commit()
    return conn.execute("SELECT * FROM gpu_tasks WHERE id = ?", (row["id"],)).fetchone()


def heartbeat(conn: sqlite3.Connection, task_id: str, progress: float) -> bool:
    """Returns False if the task is no longer this agent's to run (requeued
    by an expiry sweep, cancelled, or unknown) — the agent must abort it."""
    cursor = conn.execute(
        "UPDATE gpu_tasks SET last_heartbeat_at = ?, progress = ? "
        "WHERE id = ? AND status = 'leased'",
        (iso_now(), progress, task_id),
    )
    conn.commit()
    return cursor.rowcount == 1


def complete_task(conn: sqlite3.Connection, task_id: str, result_path: Path) -> bool:
    cursor = conn.execute(
        "UPDATE gpu_tasks SET status = 'done', result_path = ?, progress = 100, finished_at = ? "
        "WHERE id = ? AND status = 'leased'",
        (str(result_path), iso_now(), task_id),
    )
    conn.commit()
    return cursor.rowcount == 1


def fail_task(conn: sqlite3.Connection, task_id: str, error: str) -> bool:
    """Agent-reported engine failure. Fails immediately (no requeue): the
    agent only leases work after its own GPU/yield checks passed, so a crash
    here is near-certainly deterministic for this input — retrying would
    just burn GPU minutes before the same fallback."""
    cursor = conn.execute(
        "UPDATE gpu_tasks SET status = 'failed', error = ?, finished_at = ? "
        "WHERE id = ? AND status = 'leased'",
        (error[:2000], iso_now(), task_id),
    )
    conn.commit()
    return cursor.rowcount == 1


def cancel_task(conn: sqlite3.Connection, task_id: str) -> None:
    conn.execute(
        "UPDATE gpu_tasks SET status = 'cancelled', finished_at = ? "
        "WHERE id = ? AND status IN ('queued', 'leased')",
        (iso_now(), task_id),
    )
    conn.commit()


async def wait_for_task(
    db_path: Path,
    task_id: str,
    settings: Settings,
    cancelled: Optional[Callable[[], bool]] = None,
    poll_interval_s: float = WAIT_POLL_INTERVAL_S,
) -> sqlite3.Row:
    """Await a submitted task from inside a pipeline stage. Returns the done
    row (result_path set). Raises GpuTaskFailed on failure, exhausted
    attempts, or overall timeout; propagates the pipeline's own cancel by
    cancelling the task and raising GpuTaskFailed(cancelled=True)-shaped
    message (the stage's normal cancelled() check does the rest)."""
    deadline = asyncio.get_event_loop().time() + settings.worker_task_wait_timeout_s
    while True:
        conn = get_connection(db_path)
        try:
            if cancelled is not None and cancelled():
                cancel_task(conn, task_id)
                raise GpuTaskFailed("job cancelled while waiting on the GPU worker")
            sweep_expired_leases(conn, settings)
            row = conn.execute("SELECT * FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise GpuTaskFailed(f"gpu task {task_id} vanished")
            if row["status"] == "done":
                return row
            if row["status"] == "failed":
                raise GpuTaskFailed(row["error"] or "gpu task failed")
            if row["status"] == "cancelled":
                raise GpuTaskFailed("gpu task cancelled")
            if asyncio.get_event_loop().time() >= deadline:
                cancel_task(conn, task_id)
                raise GpuTaskFailed(
                    f"gpu task {task_id} timed out after {settings.worker_task_wait_timeout_s:.0f}s"
                )
        finally:
            conn.close()
        await asyncio.sleep(poll_interval_s)


# --- signed one-time input URLs -------------------------------------------

def mint_signed_url(
    conn: sqlite3.Connection, gpu_task_id: str, path: str, settings: Settings
) -> str:
    """Returns the token; the API layer turns it into /api/worker/files/{token}.
    The token IS the credential (engine subprocesses fetch without headers),
    so it's full-entropy `secrets` randomness — NOT new_id()'s UUIDv7, whose
    leading bits are a predictable timestamp — single-use, short-lived."""
    token = secrets.token_urlsafe(32)
    expires = (
        datetime.now(timezone.utc) + timedelta(seconds=settings.worker_signed_url_ttl_s)
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    conn.execute(
        "INSERT INTO signed_urls (token, gpu_task_id, path, expires_at) VALUES (?, ?, ?, ?)",
        (token, gpu_task_id, path, expires),
    )
    conn.commit()
    return token


def consume_signed_url(conn: sqlite3.Connection, token: str) -> str | None:
    """Marks the token used and returns its path, or None if unknown,
    expired, or already used."""
    row = conn.execute("SELECT * FROM signed_urls WHERE token = ?", (token,)).fetchone()
    if row is None or row["used"] or row["expires_at"] < iso_now():
        return None
    conn.execute("UPDATE signed_urls SET used = 1 WHERE token = ?", (token,))
    conn.commit()
    return row["path"]
