"""API-level tests for task-17's post-render tools: candidate picker,
image swap, scene re-render, mode re-render. These check the endpoint
contracts (status codes, request/response shapes, DB side effects); the
actual reassemble pipeline correctness (frame-hash/SSIM proof that
untouched scenes stay visually intact) is covered by the real-ffmpeg
integration test in tests/test_rerender_scene_pipeline.py - this file
doesn't re-run real ffmpeg, it seeds completed projects directly the same
way test_api_video.py's own _seed_completed_output does.
"""
import json
import sqlite3
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


def _accepted_project(c: TestClient, app, mode: str = "b") -> dict:
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


def _seed_rendered_mode_b_project(app, c, project, settings) -> Path:
    """A completed Mode B project with two scenes' images (including
    cached alternates in meta_json, matching image_service.py's retrofit)
    - enough for the candidate/swap endpoints without a real ffmpeg render."""
    project_dir = settings.media_root / "users" / project["user_id"] / "projects" / project["id"]
    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True)
    for scene_id in (1, 2):
        (images_dir / f"scene-{scene_id}.jpg").write_bytes(b"\xff\xd8\xff\xe0-fake-jpeg")

    output_path = project_dir / "output.mp4"
    output_path.write_bytes(b"fake-mp4-bytes")

    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "UPDATE projects SET output_path = ?, mode = 'b', status = 'done' WHERE id = ?",
        (str(output_path), project["id"]),
    )
    scene1_meta = {
        "engine": "pexels", "source": "pexels", "source_id": "winner-1",
        "width": 1200, "height": 1900, "url": "https://example.com/1.jpg",
        "photographer": "Alice", "photographer_url": "https://example.com/alice",
        "alternates": [
            {
                "source": "pexels", "source_id": "alt-1a", "width": 1200, "height": 1900,
                "url": "https://example.com/1a.jpg", "photographer": "Bob", "photographer_url": None,
            },
            {
                "source": "pixabay", "source_id": "alt-1b", "width": 1080, "height": 1920,
                "url": "https://example.com/1b.jpg", "photographer": "Carol", "photographer_url": None,
            },
        ],
    }
    scene2_meta = {
        "engine": "genai", "source": "genai", "source_id": "winner-2",
        "width": 1080, "height": 1920, "url": None, "photographer": None, "photographer_url": None,
        "alternates": [],
    }
    conn.execute(
        "INSERT INTO media_assets (id, project_id, kind, scene_id, path, meta_json) VALUES (?, ?, 'image', 1, ?, ?)",
        ("ma1", project["id"], str(images_dir / "scene-1.jpg"), json.dumps(scene1_meta, ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO media_assets (id, project_id, kind, scene_id, path, meta_json) VALUES (?, ?, 'image', 2, ?, ?)",
        ("ma2", project["id"], str(images_dir / "scene-2.jpg"), json.dumps(scene2_meta, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return project_dir


# --- GET candidates ---------------------------------------------------------


def test_get_candidates_returns_current_and_cached_alternates(client):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    resp = c.get(f"/api/projects/{project['id']}/scenes/1/candidates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current"]["source_id"] == "winner-1"
    assert {a["source_id"] for a in body["alternates"]} == {"alt-1a", "alt-1b"}
    assert body["can_generate_new"] is True


def test_get_candidates_genai_winner_has_no_alternates(client):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    resp = c.get(f"/api/projects/{project['id']}/scenes/2/candidates")
    assert resp.status_code == 200
    assert resp.json()["alternates"] == []


def test_get_candidates_404s_for_mode_a_project(client, monkeypatch):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()

    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE projects SET mode = 'a' WHERE id = ?", (project["id"],))
    conn.commit()
    conn.close()

    resp = c.get(f"/api/projects/{project['id']}/scenes/1/candidates")
    assert resp.status_code == 400
    assert "mode b" in resp.json()["error"]["message"].lower() or "image video" in resp.json()["error"]["message"].lower()


def test_get_candidates_404s_for_unknown_scene(client):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    resp = c.get(f"/api/projects/{project['id']}/scenes/999/candidates")
    assert resp.status_code == 404


# --- POST swap image ---------------------------------------------------------


def test_swap_image_to_a_cached_alternate_enqueues_rerender_job(client, monkeypatch):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    # Alternates only ever carry metadata (url/photographer), never cached
    # bytes - downloading a picked one is a real HTTP fetch in production.
    # Stub it here so this test exercises the endpoint's own logic (pick
    # the right alternate, update meta_json, enqueue the job), not a real
    # network call to a fake fixture URL.
    from app.services import image_service

    async def fake_download(candidate, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\xff\xd8\xff\xe0-fake")

    monkeypatch.setattr(image_service, "download_candidate", fake_download)

    resp = c.post(f"/api/projects/{project['id']}/scenes/1/image", json={"source_id": "alt-1a"})
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["type"] == "rerender_scene"

    row = json.loads(
        sqlite3.connect(settings.db_path).execute(
            "SELECT meta_json FROM media_assets WHERE project_id = ? AND scene_id = 1", (project["id"],)
        ).fetchone()[0]
    )
    assert row["source_id"] == "alt-1a"
    # The previous winner (winner-1) should now appear among the new alternates.
    assert "winner-1" in {a["source_id"] for a in row["alternates"]}
    assert "alt-1a" not in {a["source_id"] for a in row["alternates"]}

    project_after = c.get(f"/api/projects/{project['id']}").json()
    assert project_after["status"] == "generating"


def test_swap_image_unknown_source_id_404s(client):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    resp = c.post(f"/api/projects/{project['id']}/scenes/1/image", json={"source_id": "nonexistent"})
    assert resp.status_code == 404


def test_swap_image_requires_source_id_or_generate_new(client):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    resp = c.post(f"/api/projects/{project['id']}/scenes/1/image", json={})
    assert resp.status_code == 400


def test_swap_image_generate_new_uses_genai_engine(client, monkeypatch):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    from app.models.image import ImageCandidate
    from app.pipelines import mode_b

    class StubGenai:
        async def search(self, query, orientation, per_page=1):
            return [
                ImageCandidate(
                    source="genai", source_id="fresh-genai", width=1080, height=1920,
                    image_bytes=b"\xff\xd8\xff\xe0-fresh",
                )
            ]

    monkeypatch.setattr(mode_b, "make_genai_image_engine", lambda settings: StubGenai())

    resp = c.post(f"/api/projects/{project['id']}/scenes/1/image", json={"generate_new": True})
    assert resp.status_code == 201, resp.text

    row = json.loads(
        sqlite3.connect(settings.db_path).execute(
            "SELECT meta_json FROM media_assets WHERE project_id = ? AND scene_id = 1", (project["id"],)
        ).fetchone()[0]
    )
    assert row["source_id"] == "fresh-genai"


# --- POST scene rerender -----------------------------------------------------


def test_scene_rerender_enqueues_with_retts_and_resource_image(client):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    resp = c.post(f"/api/projects/{project['id']}/scenes/1/rerender", json={"voice": "hi-IN-MadhurNeural"})
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["type"] == "rerender_scene"

    project_after = c.get(f"/api/projects/{project['id']}").json()
    assert project_after["status"] == "generating"


def test_scene_rerender_400s_for_a_project_that_isnt_mode_b_yet(client):
    """The project has never been rendered at all (`mode` is still None) -
    the endpoint correctly reports "not a Mode B project" rather than a
    scene-specific 404, since it genuinely isn't one yet."""
    app, c = client
    project = _accepted_project(c, app)
    resp = c.post(f"/api/projects/{project['id']}/scenes/1/rerender", json={})
    assert resp.status_code == 400


def test_scene_rerender_404s_for_a_scene_with_no_rendered_image(client):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()

    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE projects SET mode = 'b' WHERE id = ?", (project["id"],))
    conn.commit()
    conn.close()

    resp = c.post(f"/api/projects/{project['id']}/scenes/1/rerender", json={})
    assert resp.status_code == 404


# --- POST mode rerender -------------------------------------------------------


def test_mode_rerender_requires_a_rendered_project(client):
    app, c = client
    project = _accepted_project(c, app)  # accepted but never rendered - no `mode` set yet
    resp = c.post(f"/api/projects/{project['id']}/rerender", json={})
    assert resp.status_code == 400
    assert "rendered" in resp.json()["error"]["message"].lower()


def test_mode_rerender_b_to_a_requires_an_approved_avatar(client):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    resp = c.post(f"/api/projects/{project['id']}/rerender", json={})
    assert resp.status_code == 400
    assert "avatar" in resp.json()["error"]["message"].lower()


def test_mode_rerender_b_to_a_creates_a_sibling_project_and_job(client, monkeypatch):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_rendered_mode_b_project(app, c, project, settings)

    from pathlib import Path as _Path

    from app.pipelines import avatar_styling

    class StubImageStyler:
        def style(self, selfie_bytes, selfie_mime_type, persona_description):
            return b"\xff\xd8\xff\xe0-fake-portrait-jpeg"

    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: StubImageStyler())
    fixture = (_Path(__file__).parent / "fixtures" / "test_face.jpg").read_bytes()
    avatar_resp = c.post(
        "/api/avatars",
        files={"selfie": ("selfie.jpg", fixture, "image/jpeg")},
        data={"persona_description": "Astrologer", "name": "Test Avatar", "consent": "true"},
    )
    avatar = avatar_resp.json()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if c.get(f"/api/jobs/{avatar['job_id']}").json()["status"] == "awaiting_user":
            break
        time.sleep(0.02)
    c.post(f"/api/avatars/{avatar['id']}/approve")

    from app.engines.talking_head.base import TalkingHeadResult
    from app.pipelines import mode_a
    from app.engines.tts.fake import FakeTTSEngine

    class StubWav2Lip:
        async def render(self, portrait_path, wav_path, output_path):
            return TalkingHeadResult(video_path=output_path, engine="wav2lip")

    monkeypatch.setattr(mode_a, "make_tts_engine", lambda: FakeTTSEngine())
    monkeypatch.setattr(mode_a, "make_wav2lip_engine", lambda: StubWav2Lip())

    resp = c.post(f"/api/projects/{project['id']}/rerender", json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["project_id"] != project["id"]
    assert body["job"]["type"] == "render_mode_a"

    sibling = c.get(f"/api/projects/{body['project_id']}").json()
    assert sibling["mode"] == "a"
    assert sibling["accepted_version_id"] is not None

    # The original project must be untouched.
    original_after = c.get(f"/api/projects/{project['id']}").json()
    assert original_after["mode"] == "b"
    assert original_after["output_path"] is not None

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if c.get(f"/api/jobs/{body['job']['id']}").json()["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)


def test_mode_rerender_a_to_b_needs_no_avatar(client, monkeypatch):
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()

    project_dir = settings.media_root / "users" / project["user_id"] / "projects" / project["id"]
    project_dir.mkdir(parents=True)
    output_path = project_dir / "output.mp4"
    output_path.write_bytes(b"fake-mp4-bytes")
    conn = sqlite3.connect(settings.db_path)
    conn.execute(
        "UPDATE projects SET output_path = ?, mode = 'a', status = 'done' WHERE id = ?",
        (str(output_path), project["id"]),
    )
    conn.commit()
    conn.close()

    from app.engines.tts.fake import FakeTTSEngine
    from app.pipelines import mode_b

    class EmptyImageEngine:
        async def search(self, query, orientation, per_page=5):
            return []

    from app.models.image import ImageCandidate

    class FixtureImageEngine:
        async def search(self, query, orientation, per_page=1):
            return [
                ImageCandidate(
                    source="genai", source_id="x", width=1080, height=1920,
                    image_bytes=b"\xff\xd8\xff\xe0-fake",
                )
            ]

    monkeypatch.setattr(mode_b, "make_tts_engine", lambda: FakeTTSEngine())
    monkeypatch.setattr(mode_b, "make_pexels_engine", lambda settings: EmptyImageEngine())
    monkeypatch.setattr(mode_b, "make_pixabay_engine", lambda settings: EmptyImageEngine())
    monkeypatch.setattr(mode_b, "make_genai_image_engine", lambda settings: FixtureImageEngine())

    resp = c.post(f"/api/projects/{project['id']}/rerender", json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["job"]["type"] == "render_mode_b"

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if c.get(f"/api/jobs/{body['job']['id']}").json()["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)
