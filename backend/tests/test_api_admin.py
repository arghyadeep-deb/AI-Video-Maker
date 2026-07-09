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


def _make_admin(app) -> None:
    from app.db.connection import get_connection
    from tests.conftest import DEV_USER_ID

    settings = get_settings()
    conn = get_connection(settings.db_path)
    conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (DEV_USER_ID,))
    conn.commit()
    conn.close()


def test_usage_requires_admin(client):
    _, c = client
    resp = c.get("/api/admin/usage")
    assert resp.status_code == 403


def test_usage_returns_zero_counters_when_nothing_used(client):
    app, c = client
    _make_admin(app)
    resp = c.get("/api/admin/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counters"]["gemini_text"] == 0
    assert body["counters"]["genai_image"] == 0
    assert body["counters"]["zerogpu_seconds"] == 0


def test_usage_reflects_real_counts(client):
    app, c = client
    _make_admin(app)

    from app.db.connection import get_connection
    from app.quota import guards

    settings = get_settings()
    conn = get_connection(settings.db_path)
    guards.increment_usage(conn, "gemini_text", n=12)
    guards.increment_usage(conn, "genai_image", n=3)
    conn.close()

    resp = c.get("/api/admin/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counters"]["gemini_text"] == 12
    assert body["counters"]["genai_image"] == 3
