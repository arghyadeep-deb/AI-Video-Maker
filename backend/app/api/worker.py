"""Home GPU worker protocol — specs/03-design/11-gpu-worker.md, task-20a.

    agent -> VM: POST /api/worker/poll   {capabilities[], vram_free_mb}
    VM -> agent: task lease {id, kind, payload, inputs[{name,url}]} | null (long-poll)
    agent -> VM: POST /api/worker/heartbeat {task_id, progress}   (every 10 s)
    agent -> VM: POST /api/worker/complete/{task_id} + result upload (multipart)

Auth: one pre-shared token (`WORKER_TOKEN` in the VM's env) in the
`X-Worker-Token` header — owner-only infrastructure, not a user surface.
Unset token = these endpoints are disabled outright. The signed file
endpoint is the one exception: its one-time token IS the credential, so
engine subprocesses on the agent can fetch inputs without custom headers.
Nothing else on the VM is reachable with either token.
"""
import asyncio
import json
import secrets
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.core.errors import AppError, NotFoundError, UnauthorizedError
from app.db.connection import get_connection
from app.jobs import gpu_router

router = APIRouter()

POLL_WAIT_MAX_S = 25.0  # design doc: "long-poll 25 s cycles"
POLL_CHECK_INTERVAL_S = 0.5


def require_worker_token(x_worker_token: Optional[str] = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.worker_token:
        raise UnauthorizedError("Worker endpoints are not enabled on this server")
    if not x_worker_token or not secrets.compare_digest(x_worker_token, settings.worker_token):
        raise UnauthorizedError("Invalid worker token")


class PollRequest(BaseModel):
    capabilities: list[str]
    vram_free_mb: Optional[int] = None
    # Agents may ask for a shorter wait (e.g. 0 for an immediate answer in
    # tests); the server caps it at its own long-poll ceiling either way.
    wait_s: float = Field(default=20.0, ge=0.0)


class TaskInput(BaseModel):
    name: str
    url: str  # relative — the agent joins it with its configured vm_url


class TaskLease(BaseModel):
    id: str
    kind: str
    payload: dict
    inputs: list[TaskInput]


class PollResponse(BaseModel):
    task: Optional[TaskLease] = None


def _lease_response(conn: sqlite3.Connection, row: sqlite3.Row, settings: Settings) -> TaskLease:
    input_files = json.loads(row["input_files_json"] or "[]")
    inputs = [
        TaskInput(
            name=f["name"],
            url=f"/api/worker/files/{gpu_router.mint_signed_url(conn, row['id'], f['path'], settings)}",
        )
        for f in input_files
    ]
    return TaskLease(
        id=row["id"], kind=row["kind"], payload=json.loads(row["payload_json"] or "{}"), inputs=inputs
    )


@router.post("/poll", response_model=PollResponse, dependencies=[Depends(require_worker_token)])
async def poll(payload: PollRequest) -> PollResponse:
    """Long-poll: presence is stamped every check iteration (not just once)
    so a 20 s empty wait still counts as 'online' the whole way through."""
    settings = get_settings()
    wait_s = min(payload.wait_s, POLL_WAIT_MAX_S)
    deadline = asyncio.get_event_loop().time() + wait_s
    while True:
        conn = get_connection(settings.db_path)
        try:
            gpu_router.record_worker_poll(conn, payload.capabilities, payload.vram_free_mb)
            row = gpu_router.lease_next_task(conn, payload.capabilities, settings)
            if row is not None:
                return PollResponse(task=_lease_response(conn, row, settings))
        finally:
            conn.close()
        if asyncio.get_event_loop().time() >= deadline:
            return PollResponse(task=None)
        await asyncio.sleep(POLL_CHECK_INTERVAL_S)


class HeartbeatRequest(BaseModel):
    task_id: str
    progress: float = 0.0


class HeartbeatResponse(BaseModel):
    # False tells the agent the task was reclaimed (expiry sweep re-queued
    # it, or the waiting pipeline cancelled) — abort work, discard output.
    still_leased: bool


@router.post(
    "/heartbeat", response_model=HeartbeatResponse, dependencies=[Depends(require_worker_token)]
)
def heartbeat_endpoint(
    payload: HeartbeatRequest, conn: sqlite3.Connection = Depends(get_db)
) -> HeartbeatResponse:
    return HeartbeatResponse(
        still_leased=gpu_router.heartbeat(conn, payload.task_id, payload.progress)
    )


@router.post("/complete/{task_id}", dependencies=[Depends(require_worker_token)])
def complete_endpoint(
    task_id: str, result: UploadFile, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    settings = get_settings()
    task = conn.execute("SELECT * FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        raise NotFoundError(f"gpu task {task_id} not found")
    if task["status"] != "leased":
        # Lease already reclaimed (agent was too slow / task cancelled):
        # per the design doc, partial results are discarded.
        raise AppError(
            "Task is no longer leased to you", hint="The lease expired; discard this result"
        )

    out_dir = settings.media_root / "gpu_tasks" / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    # The filename comes from our own agent, but sanitize anyway: keep only
    # the basename so a hostile value can't traverse out of out_dir.
    filename = Path(result.filename or "result.bin").name
    out_path = out_dir / filename
    with out_path.open("wb") as f:
        while chunk := result.file.read(1024 * 1024):
            f.write(chunk)

    if not gpu_router.complete_task(conn, task_id, out_path):
        out_path.unlink(missing_ok=True)  # lost a race with the expiry sweep
        raise AppError(
            "Task is no longer leased to you", hint="The lease expired; discard this result"
        )
    return {"ok": True}


class FailRequest(BaseModel):
    task_id: str
    error: str


@router.post("/fail", dependencies=[Depends(require_worker_token)])
def fail_endpoint(payload: FailRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    if not gpu_router.fail_task(conn, payload.task_id, payload.error):
        raise NotFoundError(f"gpu task {payload.task_id} is not currently leased")
    return {"ok": True}


@router.get("/files/{token}")
def download_input(token: str, conn: sqlite3.Connection = Depends(get_db)):
    """One-time signed input download. No worker-token header on purpose —
    the unguessable single-use token is the credential (engine subprocesses
    fetch without custom headers). Expired/reused/unknown all 404 identically
    so the endpoint leaks nothing about which case occurred."""
    path = gpu_router.consume_signed_url(conn, token)
    if path is None:
        raise NotFoundError("Unknown or expired file token")
    return FileResponse(path)
