import json

import pytest
from fastapi.testclient import TestClient

from app.api.script import get_script_llm
from app.core.config import get_settings
from app.main import create_app
from tests.conftest import authenticate


class StubLLM:
    """Deterministic ScriptLLM stand-in for integration tests."""

    def __init__(self, contract_json: str | list[str]):
        self._responses = (
            contract_json if isinstance(contract_json, list) else [contract_json]
        )

    def generate_raw(self, prompt: str) -> str:
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


def _hindi_contract(title="व्यापार टिप्स"):
    # 5 scenes to satisfy the 60s-duration scene-count bounds (4-7).
    return json.dumps(
        {
            "title": title,
            "language": "hi",
            "scenes": [
                {"id": 1, "text": "नमस्ते दोस्तों, आज हम बात करेंगे।", "visual_hint": "friendly greeting"},
                {"id": 2, "text": "यह एक बहुत अच्छा विचार है।", "visual_hint": "lightbulb idea"},
                {"id": 3, "text": "पहला कदम है योजना बनाना।", "visual_hint": "planning notebook"},
                {"id": 4, "text": "दूसरा कदम है मेहनत करना।", "visual_hint": "hard work desk"},
                {"id": 5, "text": "धन्यवाद, फिर मिलेंगे।", "visual_hint": "friendly goodbye"},
            ],
        }
    )


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        authenticate(app)
        yield app, c
    get_settings.cache_clear()


def _create_project(c: TestClient) -> dict:
    resp = c.post(
        "/api/projects",
        json={
            "description": "बिज़नेस शुरू करने के 5 टिप्स",
            "language": "hi",
            "duration_s": 60,
            "format": "9x16",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_project(client):
    app, c = client
    project = _create_project(c)
    assert project["status"] == "drafting"
    assert project["language"] == "hi"
    assert project["latest_script_version"] is None

    fetched = c.get(f"/api/projects/{project['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == project["id"]
    assert fetched.json()["latest_script_version"] is None


def test_get_project_not_found(client):
    _, c = client
    resp = c.get("/api/projects/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_generate_script_creates_v1(client):
    app, c = client
    project = _create_project(c)
    app.dependency_overrides[get_script_llm] = lambda: StubLLM(_hindi_contract())

    resp = c.post(f"/api/projects/{project['id']}/script")
    assert resp.status_code == 201, resp.text
    version = resp.json()
    assert version["n"] == 1
    assert version["origin"] == "generated"
    assert version["scenes"][0]["text"].startswith("नमस्ते")

    project_after = c.get(f"/api/projects/{project['id']}").json()
    assert project_after["status"] == "script_ready"
    assert project_after["title"] == "व्यापार टिप्स"
    assert project_after["latest_script_version"]["id"] == version["id"]


def test_regenerate_creates_v2(client):
    app, c = client
    project = _create_project(c)
    app.dependency_overrides[get_script_llm] = lambda: StubLLM(_hindi_contract())
    c.post(f"/api/projects/{project['id']}/script")

    app.dependency_overrides[get_script_llm] = lambda: StubLLM(_hindi_contract(title="v2"))
    resp = c.post(f"/api/projects/{project['id']}/script")
    assert resp.status_code == 201
    assert resp.json()["n"] == 2

    project_after = c.get(f"/api/projects/{project['id']}").json()
    assert project_after["latest_script_version"]["n"] == 2


def test_script_validation_failure_never_persists(client):
    app, c = client
    project = _create_project(c)
    # Both attempts (initial + one retry) return romanized Hindi -> final failure.
    bad = json.dumps(
        {
            "title": "bad",
            "language": "hi",
            "scenes": [
                {"id": 1, "text": "Namaste dosto", "visual_hint": "greeting"},
                {"id": 2, "text": "Yeh accha hai", "visual_hint": "idea"},
            ],
        }
    )
    app.dependency_overrides[get_script_llm] = lambda: StubLLM([bad, bad])

    resp = c.post(f"/api/projects/{project['id']}/script")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "script_validation_failed"

    project_after = c.get(f"/api/projects/{project['id']}").json()
    assert project_after["status"] == "drafting"  # untouched, no version persisted


def test_quota_exhausted_returns_honest_message(client):
    from app.engines.script_llm import QuotaExhaustedError

    class ExhaustedLLM:
        def generate_raw(self, prompt: str) -> str:
            raise QuotaExhaustedError()

    app, c = client
    project = _create_project(c)
    app.dependency_overrides[get_script_llm] = lambda: ExhaustedLLM()

    resp = c.post(f"/api/projects/{project['id']}/script")
    assert resp.status_code == 429
    assert "resets midnight PT" in resp.json()["error"]["hint"]


def test_generate_script_blocked_by_global_daily_guard(client, monkeypatch):
    """specs/04-tasks/task-15-quotas-fairness.md: the guard rejects BEFORE
    ever calling the LLM - a global safety rail, not the LLM's own 429."""
    from app.quota import guards

    app, c = client
    project = _create_project(c)
    monkeypatch.setattr(get_settings(), "gemini_text_daily_cap", 5)
    monkeypatch.setattr(get_settings(), "gemini_text_new_script_reserve", 0)

    from app.db.connection import get_connection

    conn = get_connection(get_settings().db_path)
    guards.increment_usage(conn, "gemini_text", n=5)
    conn.close()

    calls = {"n": 0}

    class NeverCalledLLM:
        def generate_raw(self, prompt: str) -> str:
            calls["n"] += 1
            return _hindi_contract()

    app.dependency_overrides[get_script_llm] = lambda: NeverCalledLLM()
    resp = c.post(f"/api/projects/{project['id']}/script")
    assert resp.status_code == 429
    assert calls["n"] == 0  # never even reached the LLM


def test_new_script_reserve_blocks_generation_before_improve(client, monkeypatch):
    """The degradation table's "block new scripts before improvements" -
    new-script generation stops at (cap - reserve), improve-selection
    keeps working up to the full cap."""
    app, c = client
    project = _create_project(c)
    app.dependency_overrides[get_script_llm] = lambda: StubLLM(_hindi_contract())
    version = c.post(f"/api/projects/{project['id']}/script").json()

    monkeypatch.setattr(get_settings(), "gemini_text_daily_cap", 10)
    monkeypatch.setattr(get_settings(), "gemini_text_new_script_reserve", 3)

    from app.db.connection import get_connection
    from app.quota import guards

    conn = get_connection(get_settings().db_path)
    guards.increment_usage(conn, "gemini_text", n=8)  # over (10-3)=7, under 10
    conn.close()

    # A new script is blocked at the reduced threshold...
    resp = c.post(f"/api/projects/{project['id']}/script")
    assert resp.status_code == 429

    # ...but improving the existing one still works.
    app.dependency_overrides[get_script_llm] = lambda: StubLLM('{"old_span": "x", "new_span": "y"}')
    from app.services import improve_service

    monkeypatch.setattr(
        improve_service, "make_proposal", lambda *a, **k: ("नमस्ते", "नमस्कार", "नमस्कार दोस्तों।")
    )
    resp2 = c.post(
        f"/api/projects/{project['id']}/script/improve",
        json={"version_id": version["id"], "scene_id": 1, "start": 0, "end": 7},
    )
    assert resp2.status_code == 200, resp2.text
