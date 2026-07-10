"""Protocol tests for /api/worker — task-20a's Tests section:
"Integration (fake agent against dev VM): poll -> lease -> heartbeat ->
complete; kill agent mid-job -> re-queue...; token misuse rejected."
The "fake agent" is this test client itself, speaking the real protocol
over the real endpoints against the real queue."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.connection import get_connection
from app.jobs import gpu_router
from app.main import create_app

TOKEN = "test-worker-token"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setenv("WORKER_TOKEN", TOKEN)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _headers():
    return {"X-Worker-Token": TOKEN}


def _submit(kind="sadtalker", payload=None, input_files=None) -> str:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        return gpu_router.submit_task(conn, kind, payload or {}, input_files or [])
    finally:
        conn.close()


def _task_row(task_id: str):
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        return conn.execute("SELECT * FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    finally:
        conn.close()


# --- token misuse ------------------------------------------------------------

def test_poll_without_token_is_rejected(client):
    resp = client.post("/api/worker/poll", json={"capabilities": ["sadtalker"], "wait_s": 0})
    assert resp.status_code == 401


def test_poll_with_wrong_token_is_rejected(client):
    resp = client.post(
        "/api/worker/poll",
        json={"capabilities": ["sadtalker"], "wait_s": 0},
        headers={"X-Worker-Token": "wrong"},
    )
    assert resp.status_code == 401


def test_endpoints_disabled_when_no_token_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.delenv("WORKER_TOKEN", raising=False)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        resp = c.post(
            "/api/worker/poll",
            json={"capabilities": [], "wait_s": 0},
            headers={"X-Worker-Token": ""},
        )
        assert resp.status_code == 401
    get_settings.cache_clear()


def test_worker_token_grants_no_user_surface(client):
    """The worker token can ONLY lease/heartbeat/complete gpu_tasks -
    task-20a acceptance: 'worker token can only lease/complete jobs'."""
    resp = client.get("/api/projects", headers=_headers())
    assert resp.status_code == 401


# --- the protocol ------------------------------------------------------------

def test_poll_empty_queue_returns_null_task(client):
    resp = client.post(
        "/api/worker/poll",
        json={"capabilities": ["sadtalker"], "vram_free_mb": 15000, "wait_s": 0},
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["task"] is None


def test_poll_marks_worker_online_for_tier_badge(client):
    client.post(
        "/api/worker/poll",
        json={"capabilities": ["sadtalker", "scene_gen"], "vram_free_mb": 15000, "wait_s": 0},
        headers=_headers(),
    )
    tier = client.get("/api/meta/tier").json()
    assert tier["worker_online"] is True
    assert tier["active_tier"] == "worker"
    assert tier["label"] == "Generated footage available"
    assert "scene_gen" in tier["worker_capabilities"]


def test_full_protocol_round_trip(client, tmp_path):
    """poll -> lease (with signed input URL) -> download -> heartbeat ->
    complete(multipart) -> the waiting side sees done + the uploaded file."""
    input_file = tmp_path / "portrait.jpg"
    input_file.write_bytes(b"jpeg-bytes")
    task_id = _submit(
        "sadtalker", {"quality": "hd"}, [{"name": "portrait.jpg", "path": str(input_file)}]
    )

    lease = client.post(
        "/api/worker/poll",
        json={"capabilities": ["sadtalker"], "vram_free_mb": 15000, "wait_s": 0},
        headers=_headers(),
    ).json()["task"]
    assert lease["id"] == task_id
    assert lease["kind"] == "sadtalker"
    assert lease["payload"] == {"quality": "hd"}
    assert len(lease["inputs"]) == 1

    # Signed download: no worker token needed, single-use.
    url = lease["inputs"][0]["url"]
    first = client.get(url)
    assert first.status_code == 200 and first.content == b"jpeg-bytes"
    assert client.get(url).status_code == 404  # one-time

    beat = client.post(
        "/api/worker/heartbeat", json={"task_id": task_id, "progress": 40}, headers=_headers()
    )
    assert beat.json()["still_leased"] is True

    done = client.post(
        f"/api/worker/complete/{task_id}",
        files={"result": ("result.mp4", b"rendered-bytes")},
        headers=_headers(),
    )
    assert done.status_code == 200, done.text

    row = _task_row(task_id)
    assert row["status"] == "done"
    from pathlib import Path

    assert Path(row["result_path"]).read_bytes() == b"rendered-bytes"


def test_capability_negotiation_over_http(client):
    _submit("scene_gen")
    lease = client.post(
        "/api/worker/poll",
        json={"capabilities": ["sadtalker"], "wait_s": 0},
        headers=_headers(),
    ).json()["task"]
    assert lease is None  # scene_gen task never leased to a sadtalker-only agent


def test_kill_agent_mid_job_requeues_then_fails_over(client, monkeypatch):
    """The dead-agent path end to end: lease it, send no heartbeats, and the
    waiting pipeline's own sweep requeues then fails it (attempts=1 here),
    surfacing GpuTaskFailed for the tier fallback."""
    monkeypatch.setenv("WORKER_LEASE_TIMEOUT_S", "0")
    monkeypatch.setenv("WORKER_TASK_MAX_ATTEMPTS", "1")
    get_settings.cache_clear()
    settings = get_settings()

    task_id = _submit("sadtalker")
    lease = client.post(
        "/api/worker/poll",
        json={"capabilities": ["sadtalker"], "wait_s": 0},
        headers=_headers(),
    ).json()["task"]
    assert lease["id"] == task_id
    # ...agent dies here: no heartbeat, no complete...

    with pytest.raises(gpu_router.GpuTaskFailed, match="worker lost"):
        asyncio.run(
            gpu_router.wait_for_task(settings.db_path, task_id, settings, poll_interval_s=0.01)
        )


def test_complete_after_lease_reclaim_is_rejected(client, monkeypatch):
    monkeypatch.setenv("WORKER_LEASE_TIMEOUT_S", "0")
    get_settings.cache_clear()
    settings = get_settings()

    task_id = _submit("sadtalker")
    client.post(
        "/api/worker/poll",
        json={"capabilities": ["sadtalker"], "wait_s": 0},
        headers=_headers(),
    )
    conn = get_connection(settings.db_path)
    try:
        gpu_router.sweep_expired_leases(conn, settings)  # instant expiry -> requeued
    finally:
        conn.close()

    resp = client.post(
        f"/api/worker/complete/{task_id}",
        files={"result": ("result.mp4", b"stale-bytes")},
        headers=_headers(),
    )
    assert resp.status_code == 400  # partial results discarded, per the design doc
    assert _task_row(task_id)["status"] == "queued"


def test_fail_endpoint_marks_task_failed(client):
    task_id = _submit("sadtalker")
    client.post(
        "/api/worker/poll",
        json={"capabilities": ["sadtalker"], "wait_s": 0},
        headers=_headers(),
    )
    resp = client.post(
        "/api/worker/fail", json={"task_id": task_id, "error": "CUDA OOM"}, headers=_headers()
    )
    assert resp.status_code == 200
    row = _task_row(task_id)
    assert row["status"] == "failed" and "CUDA OOM" in row["error"]


def test_upload_filename_is_sanitized_to_basename(client):
    task_id = _submit("sadtalker")
    client.post(
        "/api/worker/poll",
        json={"capabilities": ["sadtalker"], "wait_s": 0},
        headers=_headers(),
    )
    client.post(
        f"/api/worker/complete/{task_id}",
        files={"result": ("../../escape.mp4", b"x")},
        headers=_headers(),
    )
    row = _task_row(task_id)
    from pathlib import Path

    result = Path(row["result_path"])
    assert result.name == "escape.mp4"
    settings = get_settings()
    # Landed inside the task's own dir, not traversed out of it.
    assert result.parent == settings.media_root / "gpu_tasks" / task_id
