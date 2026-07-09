import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from tests.conftest import authenticate


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        authenticate(app)
        yield app, c
    get_settings.cache_clear()


def _poll_until_terminal(c: TestClient, job_id: str, timeout_s: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = c.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "failed", "cancelled"):
            return body
        time.sleep(0.02)
    raise AssertionError("job did not reach a terminal state in time")


def test_create_and_poll_debug_noop_job(client):
    _, c = client
    resp = c.post("/api/jobs/debug/noop")
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["status"] == "queued"
    assert job["type"] == "noop_render"
    assert job["stages"] == ["warm_up", "cook", "cool_down"]

    final = _poll_until_terminal(c, job["id"])
    assert final["status"] == "done"
    assert final["progress"] == 100


def test_get_unknown_job_returns_404(client):
    _, c = client
    resp = c.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404


def test_cancel_job_transitions_to_cancelled(client):
    _, c = client
    job = c.post("/api/jobs/debug/noop").json()

    # Give the worker a moment to actually claim it before cancelling.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if c.get(f"/api/jobs/{job['id']}").json()["status"] == "running":
            break
        time.sleep(0.01)

    resp = c.post(f"/api/jobs/{job['id']}/cancel")
    assert resp.status_code == 200

    final = _poll_until_terminal(c, job["id"])
    assert final["status"] == "cancelled"


def test_cancel_unknown_job_returns_404(client):
    _, c = client
    resp = c.post("/api/jobs/does-not-exist/cancel")
    assert resp.status_code == 404
