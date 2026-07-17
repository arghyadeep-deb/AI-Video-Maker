import json
import time
import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engines.tts.fake import FakeTTSEngine
from app.jobs.pipelines import noop  # noqa: F401
from app.main import create_app
from tests.conftest import authenticate
from app.models.image import ImageCandidate
from app.pipelines import mode_b


class EmptyImageEngine:
    async def search(self, query, orientation, per_page=5):
        return []


class FixtureImageEngine:
    async def search(self, query, orientation, per_page=5):
        return [
            ImageCandidate(
                source="genai", source_id=f"fixture-{query}", width=1080, height=1920,
                image_bytes=b"\xff\xd8\xff\xe0not-a-real-jpeg-but-fine-for-mocked-download",
            )
        ]


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


def _accepted_project(c: TestClient, app, duration_s: int = 30) -> dict:
    """Create + generate + accept a project via the real endpoints, using a
    stub script LLM (no real Gemini key here)."""
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
        json={"description": "d", "language": "hi", "duration_s": duration_s, "format": "9x16"},
    )
    project = resp.json()
    app.dependency_overrides[get_script_llm] = lambda: StubScriptLLM()
    c.post(f"/api/projects/{project['id']}/script")
    c.post(f"/api/projects/{project['id']}/script/accept")
    return c.get(f"/api/projects/{project['id']}").json()


def _approved_avatar(c: TestClient, monkeypatch) -> dict:
    """Creates and approves an avatar via the real endpoints, stubbing the
    image styler (no real GEMINI_API_KEY here) - same stub pattern as
    test_api_avatars.py's StubImageStyler."""
    from pathlib import Path

    from app.pipelines import avatar_styling

    class StubImageStyler:
        def style(self, selfie_bytes, selfie_mime_type, persona_description):
            return b"\xff\xd8\xff\xe0-fake-portrait-jpeg"

    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: StubImageStyler())

    fixture = (Path(__file__).parent / "fixtures" / "test_face.jpg").read_bytes()
    resp = c.post(
        "/api/avatars",
        files={"selfie": ("selfie.jpg", fixture, "image/jpeg")},
        data={"persona_description": "Astrologer", "name": "Test Avatar", "consent": "true"},
    )
    avatar = resp.json()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if c.get(f"/api/jobs/{avatar['job_id']}").json()["status"] == "awaiting_user":
            break
        time.sleep(0.02)
    c.post(f"/api/avatars/{avatar['id']}/approve")
    return c.get(f"/api/avatars/{avatar['id']}").json()


def test_create_render_job_requires_accepted_script(client):
    _, c = client
    resp = c.post("/api/projects", json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"})
    project = resp.json()

    create_resp = c.post(f"/api/projects/{project['id']}/video", json={"mode": "b"})
    assert create_resp.status_code == 400


def test_create_render_job_persists_the_requested_stock_voice(client):
    """The generate page's male/female picker sends `voice` on the render
    request - real bug found live 2026-07-16: this field didn't exist at
    all (it was called voice_profile_id and nothing ever read it), so the
    picker was pure decoration - every render silently used the enrolled
    voice or, failing that, always the hardcoded female stock default,
    regardless of what the user picked. project.voice must reflect the
    request (stage_tts's own `project["voice"] or default` lookup relies
    on this column being set correctly before the pipeline runs)."""
    app, c = client
    project = _accepted_project(c, app)

    resp = c.post(
        f"/api/projects/{project['id']}/video",
        json={"mode": "b", "voice": "hi-IN-MadhurNeural"},
    )
    assert resp.status_code == 201
    updated = c.get(f"/api/projects/{project['id']}").json()
    assert updated["voice"] == "hi-IN-MadhurNeural"


def test_create_render_job_accepts_footage_level_with_no_worker_online(client):
    """task-23: the old upfront gate rejected visual_level="footage" unless
    the home GPU worker was online, predating stage_footage's own public-
    Space tier (backend/app/engines/scene_gen/ltx_public.py) which has no
    such precondition - the request must be accepted regardless of worker
    state now; the pipeline's own per-scene fallback chain handles honest
    degradation if every tier fails, not an upfront rejection."""
    app, c = client
    project = _accepted_project(c, app)  # no worker ever registered in this test

    resp = c.post(
        f"/api/projects/{project['id']}/video",
        json={"mode": "b", "visual_level": "footage"},
    )
    assert resp.status_code == 201


def test_create_render_job_rejects_a_voice_not_in_the_projects_language(client):
    app, c = client
    project = _accepted_project(c, app)  # language="hi"

    resp = c.post(
        f"/api/projects/{project['id']}/video",
        json={"mode": "b", "voice": "en-US-AriaNeural"},
    )
    assert resp.status_code == 400


def test_create_render_job_allows_retry_after_a_failed_render(client):
    """A render job's failure/cancellation never rewrites projects.status
    back from "generating" (the worker has no notion of "project") - a
    project whose only render attempt died (crash, restart, cancel) must
    still be retryable, not permanently stuck behind the accepted-script
    gate. Real bug: found live 2026-07-15 after a server restart aborted
    an in-flight render, and the project could never be regenerated."""
    import sqlite3

    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()

    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE projects SET status = 'generating' WHERE id = ?", (project["id"],))
    conn.execute(
        "INSERT INTO jobs (id, user_id, project_id, type, status, stage, progress, payload_json) "
        "VALUES ('job-1', ?, ?, 'render_mode_b', 'failed', 'tts', 0.0, '{}')",
        (project["user_id"], project["id"]),
    )
    conn.commit()
    conn.close()

    resp = c.post(f"/api/projects/{project['id']}/video", json={"mode": "b"})
    assert resp.status_code == 201


def test_mode_a_requires_an_avatar_id(client):
    app, c = client
    project = _accepted_project(c, app)
    resp = c.post(f"/api/projects/{project['id']}/video", json={"mode": "a"})
    assert resp.status_code == 400
    assert "avatar" in resp.json()["error"]["message"].lower()


def test_mode_a_rejects_scripts_over_two_minutes(client):
    app, c = client
    from app.api.script import get_script_llm

    # A 300s script needs 20-37 scenes per script_service's own bounds
    # (duration_s // 15 to duration_s // 8) - a real script this long, not
    # the other tests' 2-scene stub.
    class LongStubScriptLLM:
        def generate_raw(self, prompt):
            return json.dumps(
                {
                    "title": "Long test video",
                    "language": "hi",
                    "scenes": [
                        {"id": i, "text": "नमस्ते दोस्तों।", "visual_hint": "greeting"}
                        for i in range(1, 26)
                    ],
                }
            )

    resp = c.post(
        "/api/projects",
        json={"description": "d", "language": "hi", "duration_s": 300, "format": "9x16"},
    )
    project = resp.json()
    app.dependency_overrides[get_script_llm] = lambda: LongStubScriptLLM()
    c.post(f"/api/projects/{project['id']}/script")
    c.post(f"/api/projects/{project['id']}/script/accept")
    project = c.get(f"/api/projects/{project['id']}").json()
    assert project["status"] == "accepted"

    resp = c.post(
        f"/api/projects/{project['id']}/video", json={"mode": "a", "avatar_id": "whatever"}
    )
    assert resp.status_code == 400
    assert "too long" in resp.json()["error"]["message"].lower()


def test_mode_a_rejects_an_unapproved_avatar(client, monkeypatch):
    app, c = client
    project = _accepted_project(c, app)

    from app.pipelines import avatar_styling

    class StubImageStyler:
        def style(self, selfie_bytes, selfie_mime_type, persona_description):
            return b"\xff\xd8\xff\xe0-fake"

    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: StubImageStyler())
    from pathlib import Path

    fixture = (Path(__file__).parent / "fixtures" / "test_face.jpg").read_bytes()
    avatar_resp = c.post(
        "/api/avatars",
        files={"selfie": ("selfie.jpg", fixture, "image/jpeg")},
        data={"persona_description": "Astrologer", "name": "Unapproved", "consent": "true"},
    )
    avatar_id = avatar_resp.json()["id"]  # never approved

    resp = c.post(
        f"/api/projects/{project['id']}/video", json={"mode": "a", "avatar_id": avatar_id}
    )
    assert resp.status_code == 400
    assert "approved" in resp.json()["error"]["message"].lower()


def test_mode_a_enqueues_and_flips_project_to_generating(client, monkeypatch):
    app, c = client
    project = _accepted_project(c, app)
    avatar = _approved_avatar(c, monkeypatch)

    from app.engines.talking_head.base import TalkingHeadResult
    from app.pipelines import mode_a

    class StubWav2Lip:
        async def render(self, portrait_path, wav_path, output_path):
            return TalkingHeadResult(video_path=output_path, engine="wav2lip")

    monkeypatch.setattr(mode_a, "make_tts_engine", lambda: FakeTTSEngine())
    monkeypatch.setattr(mode_a, "make_wav2lip_engine", lambda: StubWav2Lip())

    resp = c.post(
        f"/api/projects/{project['id']}/video",
        json={"mode": "a", "avatar_id": avatar["id"]},
    )
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["type"] == "render_mode_a"
    assert job["stages"] == ["tts", "animate", "assemble"]

    project_after = c.get(f"/api/projects/{project['id']}").json()
    assert project_after["status"] == "generating"
    assert project_after["mode"] == "a"

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if c.get(f"/api/jobs/{job['id']}").json()["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)


def test_create_render_job_enqueues_and_flips_project_to_generating(client, monkeypatch):
    """Checks the API contract (enqueue + status transition), not full
    pipeline success - FakeTTSEngine/FixtureImageEngine here write
    placeholder (non-decodable) bytes, so the background job will actually
    fail once it reaches the real-ffmpeg assemble stage. The full,
    genuinely-completing pipeline (real audio/image fixtures) is covered by
    test_mode_b_pipeline.py; this test just isn't the place for it.
    """
    app, c = client
    project = _accepted_project(c, app)

    monkeypatch.setattr(mode_b, "make_tts_engine", lambda: FakeTTSEngine())
    monkeypatch.setattr(mode_b, "make_pexels_engine", lambda settings: EmptyImageEngine())
    monkeypatch.setattr(mode_b, "make_pixabay_engine", lambda settings: EmptyImageEngine())
    monkeypatch.setattr(mode_b, "make_genai_image_engine", lambda settings: FixtureImageEngine())

    resp = c.post(f"/api/projects/{project['id']}/video", json={"mode": "b"})
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["type"] == "render_mode_b"
    assert job["stages"] == ["tts", "images", "footage", "subtitles", "assemble", "finalize"]

    project_after = c.get(f"/api/projects/{project['id']}").json()
    assert project_after["status"] == "generating"
    assert project_after["mode"] == "b"

    # Let the background job reach a terminal state before the fixture tears
    # down the app (and its worker) - avoids a dangling in-flight job.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if c.get(f"/api/jobs/{job['id']}").json()["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)


def test_stream_video_404_before_render_completes(client):
    app, c = client
    project = _accepted_project(c, app)
    resp = c.get(f"/api/projects/{project['id']}/video")
    assert resp.status_code == 404


def test_stream_video_supports_range_requests(client):
    """specs/04-tasks/task-13-library-delivery.md: "range-request streaming
    verified" - FastAPI's FileResponse handles Range headers natively, but
    this proves it rather than assuming it."""
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    output_path = _seed_completed_output(app, c, project, settings)
    video_bytes = b"0123456789" * 100  # 1000 bytes, easy to slice and check
    output_path.write_bytes(video_bytes)

    resp = c.get(f"/api/projects/{project['id']}/video", headers={"Range": "bytes=100-199"})
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 100-199/1000"
    assert resp.content == video_bytes[100:200]


def test_download_404_before_render_completes(client):
    app, c = client
    project = _accepted_project(c, app)
    resp = c.get(f"/api/projects/{project['id']}/video/download")
    assert resp.status_code == 404


def _seed_completed_output(app, c, project, settings):
    project_dir = settings.media_root / "users" / project["user_id"] / "projects" / project["id"]
    (project_dir / "subs").mkdir(parents=True)
    (project_dir / "subs" / "subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    (project_dir / "credits.txt").write_text("Image credits\n", encoding="utf-8")
    output_path = project_dir / "output.mp4"
    output_path.write_bytes(b"fake-mp4-bytes")

    import sqlite3

    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE projects SET output_path = ? WHERE id = ?", (str(output_path), project["id"]))
    conn.commit()
    conn.close()
    return output_path


def test_download_bundles_video_srt_and_credits(client):
    """Doesn't run the real ffmpeg pipeline (covered by test_mode_b_pipeline.py)
    - seeds a fake completed project directly to test the download endpoint's
    own bundling logic in isolation."""
    app, c = client
    project = _accepted_project(c, app)
    settings = get_settings()
    _seed_completed_output(app, c, project, settings)

    resp = c.get(f"/api/projects/{project['id']}/video/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(BytesIO(resp.content))
    names = set(zf.namelist())
    assert names == {"video.mp4", "subtitles.srt", "credits.txt"}
    assert zf.read("video.mp4") == b"fake-mp4-bytes"


def test_download_with_devanagari_title_does_not_crash(client):
    """Regression test: a project titled in Devanagari (the realistic case
    for this product - titles come from the script LLM in the project's own
    language) used to crash with UnicodeEncodeError, because HTTP header
    values must be Latin-1 and a bare non-ASCII Content-Disposition filename
    violates that. Found via live browser verification during task-09.
    """
    app, c = client
    from app.api.script import get_script_llm

    class DevanagariTitleLLM:
        def generate_raw(self, prompt):
            return json.dumps(
                {
                    "title": "व्यापार टिप्स",
                    "language": "hi",
                    "scenes": [
                        {"id": 1, "text": "नमस्ते दोस्तों।", "visual_hint": "greeting"},
                        {"id": 2, "text": "यह एक परीक्षण है।", "visual_hint": "test"},
                    ],
                }
            )

    resp = c.post("/api/projects", json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"})
    project = resp.json()
    app.dependency_overrides[get_script_llm] = lambda: DevanagariTitleLLM()
    c.post(f"/api/projects/{project['id']}/script")
    c.post(f"/api/projects/{project['id']}/script/accept")
    project = c.get(f"/api/projects/{project['id']}").json()
    assert project["title"] == "व्यापार टिप्स"

    settings = get_settings()
    _seed_completed_output(app, c, project, settings)

    resp = c.get(f"/api/projects/{project['id']}/video/download")
    assert resp.status_code == 200, resp.text
    disposition = resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert "व्यापार" not in disposition  # raw Devanagari must never appear in a raw header string
