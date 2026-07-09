import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.ids import new_id
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


def _make_test_mp4(path, duration_s: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=blue:s=64x64:d={duration_s}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_s}",
            "-shortest", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True, capture_output=True, timeout=20,
    )


def _stuck_job(conn, user_id: str, expected_duration_s: float | None = None) -> str:
    # Inserted directly as already-failed - render_mode_a's real pipeline
    # doesn't exist until task-12, and enqueueing through the live worker
    # would race its poll loop for no reason (import-render only cares
    # about the job row's payload/status, not about actually running it).
    payload = {"expected_duration_s": expected_duration_s} if expected_duration_s is not None else {}
    job_id = new_id()
    conn.execute(
        "INSERT INTO jobs (id, user_id, project_id, type, status, stage, progress, payload_json, error) "
        "VALUES (?, ?, NULL, 'render_mode_a', 'failed', NULL, 0, ?, 'stuck')",
        (job_id, user_id, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    return job_id


def _make_admin(conn, user_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (?, ?, ?)",
        (user_id, "dev@local", "unset"),
    )
    conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    conn.commit()


def _dev_connection(app):
    from app.db.connection import get_connection
    from tests.conftest import DEV_USER_ID

    settings = get_settings()
    conn = get_connection(settings.db_path)
    return conn, DEV_USER_ID


def test_import_render_requires_admin(client, tmp_path):
    app, c = client
    conn, dev_user_id = _dev_connection(app)
    conn.execute(
        "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (?, ?, ?)",
        (dev_user_id, "dev@local", "unset"),
    )
    conn.commit()
    job_id = _stuck_job(conn, dev_user_id)
    conn.close()

    video_path = tmp_path / "render.mp4"
    _make_test_mp4(video_path, 5.0)

    with open(video_path, "rb") as f:
        resp = c.post(f"/api/jobs/{job_id}/import-render", files={"video": ("render.mp4", f, "video/mp4")})
    assert resp.status_code == 403


def test_import_render_succeeds_for_admin_with_matching_duration(client, tmp_path):
    app, c = client
    conn, dev_user_id = _dev_connection(app)
    _make_admin(conn, dev_user_id)
    job_id = _stuck_job(conn, dev_user_id, expected_duration_s=5.0)
    conn.close()

    video_path = tmp_path / "render.mp4"
    _make_test_mp4(video_path, 5.2)  # within +/-2s tolerance

    with open(video_path, "rb") as f:
        resp = c.post(f"/api/jobs/{job_id}/import-render", files={"video": ("render.mp4", f, "video/mp4")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done"
    assert body["progress"] == 100


def test_import_render_rejects_mismatched_duration(client, tmp_path):
    app, c = client
    conn, dev_user_id = _dev_connection(app)
    _make_admin(conn, dev_user_id)
    job_id = _stuck_job(conn, dev_user_id, expected_duration_s=5.0)
    conn.close()

    video_path = tmp_path / "render.mp4"
    _make_test_mp4(video_path, 12.0)  # way outside +/-2s tolerance

    with open(video_path, "rb") as f:
        resp = c.post(f"/api/jobs/{job_id}/import-render", files={"video": ("render.mp4", f, "video/mp4")})
    assert resp.status_code == 400
    assert "duration" in resp.json()["error"]["message"].lower()

    # The job must still be in its original (failed) state - a rejected
    # import must not silently mark a stuck job as done anyway.
    job_after = c.get(f"/api/jobs/{job_id}").json()
    assert job_after["status"] == "failed"


def test_import_render_unknown_job_404s(client, tmp_path):
    app, c = client
    conn, dev_user_id = _dev_connection(app)
    _make_admin(conn, dev_user_id)
    conn.close()

    video_path = tmp_path / "render.mp4"
    _make_test_mp4(video_path, 5.0)

    with open(video_path, "rb") as f:
        resp = c.post("/api/jobs/does-not-exist/import-render", files={"video": ("render.mp4", f, "video/mp4")})
    assert resp.status_code == 404


def test_import_render_skips_duration_check_when_no_expectation_recorded(client, tmp_path):
    app, c = client
    conn, dev_user_id = _dev_connection(app)
    _make_admin(conn, dev_user_id)
    job_id = _stuck_job(conn, dev_user_id, expected_duration_s=None)
    conn.close()

    video_path = tmp_path / "render.mp4"
    _make_test_mp4(video_path, 30.0)

    with open(video_path, "rb") as f:
        resp = c.post(f"/api/jobs/{job_id}/import-render", files={"video": ("render.mp4", f, "video/mp4")})
    assert resp.status_code == 200, resp.text
