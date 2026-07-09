import json

import pytest
from fastapi.testclient import TestClient

from app.api.script import get_script_llm
from app.core.config import get_settings
from app.main import create_app
from tests.conftest import authenticate


class StubLLM:
    def __init__(self, contract_json: str):
        self._response = contract_json

    def generate_raw(self, prompt: str) -> str:
        return self._response


def _hindi_contract(title="व्यापार टिप्स"):
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


def _create_project_with_script(app, c: TestClient) -> dict:
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
    app.dependency_overrides[get_script_llm] = lambda: StubLLM(_hindi_contract())
    c.post(f"/api/projects/{project['id']}/script")
    return project


def test_edit_scene_creates_new_version_and_marks_stale(client):
    app, c = client
    project = _create_project_with_script(app, c)

    resp = c.put(
        f"/api/projects/{project['id']}/script/scene/2",
        json={"text": "एक बेहतर वाक्य यहाँ है।"},
    )
    assert resp.status_code == 200, resp.text
    version = resp.json()
    assert version["n"] == 2
    assert version["origin"] == "edited"

    edited_scene = next(s for s in version["scenes"] if s["id"] == 2)
    assert edited_scene["text"] == "एक बेहतर वाक्य यहाँ है।"
    assert edited_scene["visual_hint_stale"] is True

    untouched_scene = next(s for s in version["scenes"] if s["id"] == 1)
    assert untouched_scene["text"] == "नमस्ते दोस्तों, आज हम बात करेंगे।"
    assert untouched_scene["visual_hint_stale"] is False


def test_edit_unknown_scene_returns_404(client):
    app, c = client
    project = _create_project_with_script(app, c)
    resp = c.put(f"/api/projects/{project['id']}/script/scene/999", json={"text": "x"})
    assert resp.status_code == 404


def test_version_history_lists_versions_newest_first(client):
    app, c = client
    project = _create_project_with_script(app, c)
    c.put(f"/api/projects/{project['id']}/script/scene/1", json={"text": "बदला हुआ पाठ है।"})

    resp = c.get(f"/api/projects/{project['id']}/script/versions")
    assert resp.status_code == 200
    versions = resp.json()
    assert [v["n"] for v in versions] == [2, 1]
    assert versions[0]["origin"] == "edited"
    assert versions[1]["origin"] == "generated"


def test_restore_creates_new_version_with_old_content(client):
    app, c = client
    project = _create_project_with_script(app, c)
    versions_before = c.get(f"/api/projects/{project['id']}/script/versions").json()
    v1_id = versions_before[0]["id"]  # only version so far

    c.put(f"/api/projects/{project['id']}/script/scene/1", json={"text": "बदला हुआ पाठ है।"})

    resp = c.post(f"/api/projects/{project['id']}/script/restore/{v1_id}")
    assert resp.status_code == 200, resp.text
    restored = resp.json()
    assert restored["n"] == 3
    scene_1 = next(s for s in restored["scenes"] if s["id"] == 1)
    assert scene_1["text"] == "नमस्ते दोस्तों, आज हम बात करेंगे।"


def test_restore_unknown_version_returns_404(client):
    app, c = client
    project = _create_project_with_script(app, c)
    resp = c.post(f"/api/projects/{project['id']}/script/restore/does-not-exist")
    assert resp.status_code == 404


def test_accept_freezes_version_and_flips_status(client):
    app, c = client
    project = _create_project_with_script(app, c)

    resp = c.post(f"/api/projects/{project['id']}/script/accept")
    assert resp.status_code == 200, resp.text
    accepted = resp.json()
    assert accepted["status"] == "accepted"
    assert accepted["accepted_version_id"] is not None
    assert accepted["accepted_version_id"] == accepted["latest_script_version"]["id"]


def test_scrap_resets_status_to_drafting(client):
    app, c = client
    project = _create_project_with_script(app, c)
    c.post(f"/api/projects/{project['id']}/script/accept")

    resp = c.delete(f"/api/projects/{project['id']}/script")
    assert resp.status_code == 200, resp.text
    scrapped = resp.json()
    assert scrapped["status"] == "drafting"
    assert scrapped["accepted_version_id"] is None


def test_editing_and_pruning_keeps_only_ten_versions(client):
    app, c = client
    project = _create_project_with_script(app, c)  # v1 exists

    for i in range(12):  # push to v13, well past the keep-10 window
        c.put(
            f"/api/projects/{project['id']}/script/scene/1",
            json={"text": f"संस्करण संख्या {i} यहाँ है।"},
        )

    versions = c.get(f"/api/projects/{project['id']}/script/versions").json()
    assert len(versions) == 10
    assert versions[0]["n"] == 13
    assert versions[-1]["n"] == 4
