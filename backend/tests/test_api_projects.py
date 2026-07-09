import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from tests.conftest import authenticate


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        authenticate(app)
        yield app, c
    get_settings.cache_clear()


def _accepted_project(c: TestClient, app) -> dict:
    from app.api.script import get_script_llm

    class StubScriptLLM:
        def generate_raw(self, prompt):
            return json.dumps(
                {
                    "title": "Test video",
                    "language": "hi",
                    "scenes": [
                        {"id": 1, "text": "नमस्ते दोस्तों।", "visual_hint": "greeting"},
                        {"id": 2, "text": "यह एक परीक्षण है।", "visual_hint": "test"},
                    ],
                }
            )

    resp = c.post(
        "/api/projects",
        json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"},
    )
    project = resp.json()
    app.dependency_overrides[get_script_llm] = lambda: StubScriptLLM()
    c.post(f"/api/projects/{project['id']}/script")
    c.post(f"/api/projects/{project['id']}/script/accept")
    return c.get(f"/api/projects/{project['id']}").json()


def test_list_projects_is_empty_initially(client):
    _, c = client
    resp = c.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_projects_returns_newest_first(client):
    _, c = client
    first = c.post(
        "/api/projects", json={"description": "d1", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()
    second = c.post(
        "/api/projects", json={"description": "d2", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()

    resp = c.get("/api/projects")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert ids == [second["id"], first["id"]]


def test_list_projects_breaks_created_at_ties_by_id(client):
    """created_at has millisecond precision - two projects created within
    the same millisecond would tie on it alone, making "newest first"
    non-deterministic. UUIDv7 ids are themselves time-sortable, so they're
    used as the tiebreaker."""
    app, c = client
    first = c.post(
        "/api/projects", json={"description": "d1", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()
    second = c.post(
        "/api/projects", json={"description": "d2", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()

    settings = get_settings()
    from app.db.connection import get_connection

    conn = get_connection(settings.db_path)
    same_timestamp = conn.execute(
        "SELECT created_at FROM projects WHERE id = ?", (first["id"],)
    ).fetchone()["created_at"]
    conn.execute("UPDATE projects SET created_at = ? WHERE id = ?", (same_timestamp, second["id"]))
    conn.commit()
    conn.close()

    resp = c.get("/api/projects")
    ids = [p["id"] for p in resp.json()]
    assert ids == sorted([first["id"], second["id"]], reverse=True)


def test_list_projects_reports_no_thumbnail_and_no_active_job_for_a_fresh_project(client):
    _, c = client
    project = c.post(
        "/api/projects", json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()

    summary = c.get("/api/projects").json()[0]
    assert summary["id"] == project["id"]
    assert summary["has_thumbnail"] is False
    assert summary["active_job_id"] is None
    assert summary["status"] == "drafting"


def test_list_projects_reports_an_active_job(client, monkeypatch):
    """Was previously a sleep()-then-poll race (widen the sleep, hope the
    poll catches it) - flaky under full-suite system load since the window
    was still just a fixed guess. Fixed with a real synchronization
    primitive: the fake TTS signals a threading.Event the instant it's
    actually invoked (i.e. the instant the job is genuinely 'running'), so
    the test's single assertion runs right after that guaranteed point
    instead of racing to catch it mid-poll. The TTS then does a plain
    asyncio.sleep (not a blocking one) so it yields back to the event loop
    and doesn't stall the very c.get() call this test makes.
    """
    import asyncio
    import threading

    app, c = client
    project = _accepted_project(c, app)

    from app.engines.tts.fake import FakeTTSEngine
    from app.pipelines import mode_b

    started = threading.Event()

    class SignalingFakeTTS(FakeTTSEngine):
        async def speak(self, text, voice, out_path, rate=None):
            started.set()
            await asyncio.sleep(1.0)
            return await super().speak(text, voice, out_path, rate)

    monkeypatch.setattr(mode_b, "make_tts_engine", lambda: SignalingFakeTTS())

    job = c.post(f"/api/projects/{project['id']}/video", json={"mode": "b"}).json()

    assert started.wait(timeout=5.0), "job never reached 'running' within 5s"
    summaries = c.get("/api/projects").json()
    summary = next(s for s in summaries if s["id"] == project["id"])
    assert summary["active_job_id"] == job["id"]


def test_list_projects_shows_failed_status_instead_of_stuck_generating(client, monkeypatch):
    """Regression guard: a render job's failure never rewrites
    projects.status (worker.py is pipeline-agnostic) - without deriving the
    display status from the most recent job, a failed render would leave
    the project showing "generating" forever with no active job to poll."""
    app, c = client
    project = _accepted_project(c, app)

    from app.engines.tts.fake import FakeTTSEngine
    from app.pipelines import mode_b

    class ExplodingTTS(FakeTTSEngine):
        async def speak(self, text, voice, out_path, rate=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(mode_b, "make_tts_engine", lambda: ExplodingTTS())
    job = c.post(f"/api/projects/{project['id']}/video", json={"mode": "b"}).json()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if c.get(f"/api/jobs/{job['id']}").json()["status"] == "failed":
            break
        time.sleep(0.02)

    summaries = c.get("/api/projects").json()
    summary = next(s for s in summaries if s["id"] == project["id"])
    assert summary["status"] == "failed"
    assert summary["active_job_id"] is None


def test_thumbnail_404s_before_render_completes(client):
    _, c = client
    project = c.post(
        "/api/projects", json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()
    resp = c.get(f"/api/projects/{project['id']}/thumbnail")
    assert resp.status_code == 404


def test_thumbnail_served_once_present(client):
    app, c = client
    project = c.post(
        "/api/projects", json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()

    settings = get_settings()
    from app.pipelines.common import project_dir

    dir_path = project_dir(settings.media_root, project["user_id"], project["id"])
    dir_path.mkdir(parents=True)
    (dir_path / "thumbnail.jpg").write_bytes(b"fake-jpeg-bytes")

    resp = c.get(f"/api/projects/{project['id']}/thumbnail")
    assert resp.status_code == 200
    assert resp.content == b"fake-jpeg-bytes"


def test_delete_project_removes_row_and_folder(client):
    app, c = client
    project = _accepted_project(c, app)

    settings = get_settings()
    from app.pipelines.common import project_dir

    dir_path = project_dir(settings.media_root, project["user_id"], project["id"])
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "output.mp4").write_bytes(b"fake-video")
    assert dir_path.exists()

    resp = c.delete(f"/api/projects/{project['id']}")
    assert resp.status_code == 204

    assert c.get(f"/api/projects/{project['id']}").status_code == 404
    assert not dir_path.exists()
    assert project["id"] not in [p["id"] for p in c.get("/api/projects").json()]


def test_delete_unknown_project_404s(client):
    _, c = client
    resp = c.delete("/api/projects/does-not-exist")
    assert resp.status_code == 404


def test_delete_project_with_accepted_script_does_not_violate_fk_constraint(client):
    """Regression guard: projects.accepted_version_id references
    script_versions, and PRAGMA foreign_keys is ON for this connection - a
    naive delete-in-the-wrong-order would hit a FOREIGN KEY constraint
    failure here."""
    app, c = client
    project = _accepted_project(c, app)
    assert project["accepted_version_id"] is not None

    resp = c.delete(f"/api/projects/{project['id']}")
    assert resp.status_code == 204
