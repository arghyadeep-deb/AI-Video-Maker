import json

import pytest
from fastapi.testclient import TestClient

from app.api.script import get_script_llm
from app.core.config import get_settings
from app.main import create_app
from tests.conftest import authenticate


class StubGenerateLLM:
    """Only implements generate_raw (used by /script generate)."""

    def __init__(self, contract_json: str):
        self._response = contract_json

    def generate_raw(self, prompt: str) -> str:
        return self._response


class StubImproveLLM:
    """Only implements generate_text (used by /script/improve)."""

    def __init__(self, response: str):
        self._response = response
        self.prompts: list[str] = []

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._response


def _hindi_contract():
    return json.dumps(
        {
            "title": "व्यापार टिप्स",
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


def _create_project_with_script(app, c: TestClient) -> tuple[dict, dict]:
    resp = c.post(
        "/api/projects",
        json={
            "description": "बिज़नेस शुरू करने के 5 टिप्स",
            "language": "hi",
            "duration_s": 60,
            "format": "9x16",
        },
    )
    project = resp.json()
    app.dependency_overrides[get_script_llm] = lambda: StubGenerateLLM(_hindi_contract())
    version = c.post(f"/api/projects/{project['id']}/script").json()
    return project, version


def test_improve_returns_proposal_without_persisting(client):
    app, c = client
    project, version = _create_project_with_script(app, c)
    scene1_text = version["scenes"][0]["text"]
    start = scene1_text.index("आज")
    end = start + len("आज हम बात करेंगे")

    app.dependency_overrides[get_script_llm] = lambda: StubImproveLLM("अभी हम चर्चा करेंगे")
    resp = c.post(
        f"/api/projects/{project['id']}/script/improve",
        json={
            "version_id": version["id"],
            "scene_id": 1,
            "start": start,
            "end": end,
            "instruction": "make it warmer",
        },
    )
    assert resp.status_code == 200, resp.text
    proposal = resp.json()
    assert proposal["old_span"] == "आज हम बात करेंगे"
    assert proposal["new_span"] == "अभी हम चर्चा करेंगे"
    assert proposal["proposed_scene_text"] == scene1_text[:start] + "अभी हम चर्चा करेंगे" + scene1_text[end:]

    # Not persisted: still only v1, scene 1 text unchanged.
    versions = c.get(f"/api/projects/{project['id']}/script/versions").json()
    assert len(versions) == 1
    project_after = c.get(f"/api/projects/{project['id']}").json()
    assert project_after["latest_script_version"]["scenes"][0]["text"] == scene1_text


def test_improve_unknown_scene_returns_404(client):
    app, c = client
    project, version = _create_project_with_script(app, c)
    app.dependency_overrides[get_script_llm] = lambda: StubImproveLLM("x")
    resp = c.post(
        f"/api/projects/{project['id']}/script/improve",
        json={"version_id": version["id"], "scene_id": 999, "start": 0, "end": 1},
    )
    assert resp.status_code == 404


def test_improve_out_of_bounds_span_returns_400(client):
    app, c = client
    project, version = _create_project_with_script(app, c)
    app.dependency_overrides[get_script_llm] = lambda: StubImproveLLM("x")
    resp = c.post(
        f"/api/projects/{project['id']}/script/improve",
        json={"version_id": version["id"], "scene_id": 1, "start": 0, "end": 9999},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_span"


def test_improve_unknown_version_returns_404(client):
    app, c = client
    project, _ = _create_project_with_script(app, c)
    app.dependency_overrides[get_script_llm] = lambda: StubImproveLLM("x")
    resp = c.post(
        f"/api/projects/{project['id']}/script/improve",
        json={"version_id": "does-not-exist", "scene_id": 1, "start": 0, "end": 1},
    )
    assert resp.status_code == 404


def test_apply_persists_new_version_with_improved_origin(client):
    app, c = client
    project, version = _create_project_with_script(app, c)
    other_scenes_before = {s["id"]: s["text"] for s in version["scenes"] if s["id"] != 1}

    resp = c.post(
        f"/api/projects/{project['id']}/script/apply",
        json={"scene_id": 1, "proposed_scene_text": "एक बिल्कुल नया वाक्य यहाँ है।"},
    )
    assert resp.status_code == 200, resp.text
    applied = resp.json()
    assert applied["n"] == 2
    assert applied["origin"] == "improved"

    scene1 = next(s for s in applied["scenes"] if s["id"] == 1)
    assert scene1["text"] == "एक बिल्कुल नया वाक्य यहाँ है।"
    assert scene1["visual_hint_stale"] is True

    # Every other scene is byte-identical to before the apply.
    for scene in applied["scenes"]:
        if scene["id"] != 1:
            assert scene["text"] == other_scenes_before[scene["id"]]
            assert scene["visual_hint_stale"] is False


def test_apply_unknown_scene_returns_404(client):
    app, c = client
    project, _ = _create_project_with_script(app, c)
    resp = c.post(
        f"/api/projects/{project['id']}/script/apply",
        json={"scene_id": 999, "proposed_scene_text": "x"},
    )
    assert resp.status_code == 404


def test_revert_means_no_backend_call_at_all(client):
    """Revert is purely a frontend discard - there is no endpoint for it
    because /improve never persists anything in the first place."""
    app, c = client
    project, version = _create_project_with_script(app, c)
    app.dependency_overrides[get_script_llm] = lambda: StubImproveLLM("proposed but never applied")
    c.post(
        f"/api/projects/{project['id']}/script/improve",
        json={"version_id": version["id"], "scene_id": 2, "start": 0, "end": 2},
    )
    # Simply never calling /apply is "revert" - versions list proves it.
    versions = c.get(f"/api/projects/{project['id']}/script/versions").json()
    assert len(versions) == 1
