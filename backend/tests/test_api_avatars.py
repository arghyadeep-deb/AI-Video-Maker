import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engines.image_styler import ImageStyler
from app.main import create_app
from tests.conftest import authenticate
from app.pipelines import avatar_styling

FIXTURE_FACE = (Path(__file__).parent / "fixtures" / "test_face.jpg").read_bytes()


class StubImageStyler:
    def __init__(self, portrait_bytes: bytes = b"\xff\xd8\xff\xe0-fake-portrait-jpeg"):
        self._portrait_bytes = portrait_bytes
        self.calls: list[str] = []

    def style(self, selfie_bytes, selfie_mime_type, persona_description):
        self.calls.append(persona_description)
        return self._portrait_bytes


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


def _poll_until_terminal(c: TestClient, job_id: str, timeout_s: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = c.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "failed", "cancelled", "awaiting_user"):
            return body
        time.sleep(0.02)
    raise AssertionError("job did not reach a terminal-ish state in time")


def _upload(c: TestClient, **overrides):
    files = {"selfie": ("selfie.jpg", overrides.pop("selfie_bytes", FIXTURE_FACE), "image/jpeg")}
    data = {
        "persona_description": overrides.pop("persona_description", "Astrologer, saffron robes"),
        "name": overrides.pop("name", "My Avatar"),
        "consent": overrides.pop("consent", "true"),
    }
    return c.post("/api/avatars", files=files, data=data)


class UnavailableImageStyler:
    """Simulates risk R2's real July-2026 trigger: the image model's free
    tier is gone (429 limit: 0)."""

    def style(self, selfie_bytes, selfie_mime_type, persona_description):
        from app.engines.image_styler import ImageStylerUnavailableError

        raise ImageStylerUnavailableError("429 RESOURCE_EXHAUSTED limit: 0")


def test_styling_unavailable_offers_raw_selfie_at_the_approval_gate(client, monkeypatch):
    """R2 degrade (triggered 2026-07-11): styling quota gone -> the raw
    selfie becomes the portrait attempt, the job still parks awaiting_user
    (nothing auto-approves), and the reason is recorded honestly."""
    app, c = client
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: UnavailableImageStyler())

    resp = _upload(c)
    assert resp.status_code == 201, resp.text
    avatar_id = resp.json()["id"]
    job = _poll_until_terminal(c, resp.json()["job_id"])
    assert job["status"] == "awaiting_user"  # NOT failed - honest degrade

    from app.db.connection import get_connection

    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        avatar = conn.execute("SELECT * FROM avatars WHERE id = ?", (avatar_id,)).fetchone()
        portrait = Path(avatar["portrait_path"])
        selfie = Path(avatar["selfie_path"])
        assert portrait.exists()
        assert portrait.read_bytes() == selfie.read_bytes()  # the raw selfie, unstyled
        notes = conn.execute(
            "SELECT engine_notes FROM jobs WHERE id = ?", (resp.json()["job_id"],)
        ).fetchone()["engine_notes"]
        assert "styling unavailable" in notes
    finally:
        conn.close()

    # The user can still approve it - the gate works as ever.
    approve = c.post(f"/api/avatars/{avatar_id}/approve")
    assert approve.status_code == 200, approve.text


def test_upload_without_consent_is_rejected(client):
    _, c = client
    resp = _upload(c, consent="false")
    assert resp.status_code == 400
    assert "consent" in resp.json()["error"]["message"].lower()


def test_upload_with_an_impersonation_persona_is_declined(client):
    """specs/04-tasks/task-19-moderation-consent.md: "Impersonation-style
    persona requests are declined with a clear message"."""
    _, c = client
    resp = _upload(c, persona_description="make me look like Tom Cruise")
    assert resp.status_code == 400
    assert "named person" in resp.json()["error"]["message"].lower()


def test_upload_without_a_detected_face_is_rejected(client):
    _, c = client
    # A tiny solid-color JPEG has no face in it.
    import cv2
    import numpy as np

    ok, buf = cv2.imencode(".jpg", np.full((200, 200, 3), 100, dtype="uint8"))
    assert ok
    resp = _upload(c, selfie_bytes=buf.tobytes())
    assert resp.status_code == 400
    assert "no face" in resp.json()["error"]["message"].lower()


def test_upload_wrong_content_type_is_rejected(client):
    _, c = client
    files = {"selfie": ("selfie.txt", b"not an image", "text/plain")}
    data = {"persona_description": "Astrologer", "name": "x", "consent": "true"}
    resp = c.post("/api/avatars", files=files, data=data)
    assert resp.status_code == 400


def test_successful_upload_enqueues_styling_job(client, monkeypatch):
    app, c = client
    stub = StubImageStyler()
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: stub)

    resp = _upload(c)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["approved"] is False
    assert body["consented"] is True
    assert body["portrait_path"] is None
    assert body["job_id"]

    final = _poll_until_terminal(c, body["job_id"])
    assert final["status"] == "awaiting_user"
    assert stub.calls == ["Astrologer, saffron robes"]

    avatar_after = c.get(f"/api/avatars/{body['id']}").json()
    assert avatar_after["portrait_path"] is not None
    assert Path(avatar_after["portrait_path"]).exists()

    selfie_resp = c.get(f"/api/avatars/{body['id']}/selfie")
    assert selfie_resp.status_code == 200
    assert selfie_resp.content == FIXTURE_FACE

    portrait_resp = c.get(f"/api/avatars/{body['id']}/portrait")
    assert portrait_resp.status_code == 200
    assert portrait_resp.content == stub._portrait_bytes


class SlowImageStyler:
    """Deliberately slower than any real check-immediately-after-upload
    request can round-trip - without this, whether the job has already
    finished by the time the test's very next line runs is a genuine race
    (and R2's raw-selfie fallback in avatar_styling.py made the no-stub
    default path resolve near-instantly, breaking that race outright - a
    real regression this test caught)."""

    def style(self, selfie_bytes, selfie_mime_type, persona_description):
        time.sleep(0.5)
        return b"\xff\xd8\xff\xe0-fake-portrait-jpeg"


def test_portrait_endpoint_404s_before_styling_completes(client, monkeypatch):
    app, c = client
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: SlowImageStyler())
    resp = _upload(c)
    avatar_id = resp.json()["id"]
    portrait_resp = c.get(f"/api/avatars/{avatar_id}/portrait")
    assert portrait_resp.status_code == 404


class CrashingImageStyler:
    """A genuine crash (NOT ImageStylerUnavailableError) - the R2 degrade
    must not swallow real bugs, so this leaves the avatar portrait-less."""

    def style(self, selfie_bytes, selfie_mime_type, persona_description):
        raise RuntimeError("styler exploded")


def test_approve_requires_a_styled_portrait_first(client, monkeypatch):
    app, c = client
    # Deterministically portrait-less: the styling job fails outright.
    # (Before the repo-root .env held real keys, "no styler configured" made
    # this implicit; now it must be explicit or the test would hit the real
    # network and race the worker.)
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: CrashingImageStyler())
    resp = _upload(c)
    avatar_id = resp.json()["id"]
    job = _poll_until_terminal(c, resp.json()["job_id"])
    assert job["status"] == "failed"  # a real crash still fails honestly
    # Approve with no portrait on file should fail cleanly rather than
    # approving an empty portrait.
    approve_resp = c.post(f"/api/avatars/{avatar_id}/approve")
    assert approve_resp.status_code == 400


def test_full_approval_flow(client, monkeypatch):
    app, c = client
    stub = StubImageStyler()
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: stub)

    resp = _upload(c)
    avatar_id = resp.json()["id"]
    _poll_until_terminal(c, resp.json()["job_id"])

    approve_resp = c.post(f"/api/avatars/{avatar_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["approved"] is True

    listed = c.get("/api/avatars").json()
    assert any(a["id"] == avatar_id for a in listed)


def test_unapproved_avatars_are_not_in_the_reuse_list(client, monkeypatch):
    app, c = client
    stub = StubImageStyler()
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: stub)

    resp = _upload(c)
    avatar_id = resp.json()["id"]
    _poll_until_terminal(c, resp.json()["job_id"])

    listed = c.get("/api/avatars").json()
    assert not any(a["id"] == avatar_id for a in listed)


def test_restyle_creates_a_new_job_and_resets_approval(client, monkeypatch):
    app, c = client
    stub = StubImageStyler()
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: stub)

    resp = _upload(c)
    avatar_id = resp.json()["id"]
    _poll_until_terminal(c, resp.json()["job_id"])
    c.post(f"/api/avatars/{avatar_id}/approve")

    restyle_resp = c.post(f"/api/avatars/{avatar_id}/restyle", json={"persona_description": "Businessman, suit"})
    assert restyle_resp.status_code == 200
    body = restyle_resp.json()
    assert body["approved"] is False  # re-approval required after restyle
    assert body["job_id"]

    _poll_until_terminal(c, body["job_id"])
    assert stub.calls == ["Astrologer, saffron robes", "Businessman, suit"]


def test_restyle_with_an_impersonation_persona_is_declined(client, monkeypatch):
    app, c = client
    stub = StubImageStyler()
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: stub)

    resp = _upload(c)
    avatar_id = resp.json()["id"]
    _poll_until_terminal(c, resp.json()["job_id"])

    restyle_resp = c.post(
        f"/api/avatars/{avatar_id}/restyle", json={"persona_description": "dress up as Albert Einstein"}
    )
    assert restyle_resp.status_code == 400
    assert "named person" in restyle_resp.json()["error"]["message"].lower()


def test_restyle_keeps_the_previous_portrait_file(client, monkeypatch):
    """specs/04-tasks/task-10-avatar-styling.md's own Implementation notes:
    'previous portraits kept until approval (pick between attempts)' - a
    restyle must not destroy the prior attempt's file."""
    app, c = client
    stub = StubImageStyler(portrait_bytes=b"\xff\xd8\xff\xe0-attempt-one")
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: stub)

    resp = _upload(c)
    avatar_id = resp.json()["id"]
    _poll_until_terminal(c, resp.json()["job_id"])
    first_portrait_path = Path(c.get(f"/api/avatars/{avatar_id}").json()["portrait_path"])
    assert first_portrait_path.read_bytes() == b"\xff\xd8\xff\xe0-attempt-one"

    stub._portrait_bytes = b"\xff\xd8\xff\xe0-attempt-two"
    restyle_resp = c.post(f"/api/avatars/{avatar_id}/restyle", json={"persona_description": "Businessman, suit"})
    _poll_until_terminal(c, restyle_resp.json()["job_id"])
    second_portrait_path = Path(c.get(f"/api/avatars/{avatar_id}").json()["portrait_path"])

    assert second_portrait_path != first_portrait_path
    assert first_portrait_path.exists(), "the first attempt's file must survive a restyle"
    assert first_portrait_path.read_bytes() == b"\xff\xd8\xff\xe0-attempt-one"
    assert second_portrait_path.read_bytes() == b"\xff\xd8\xff\xe0-attempt-two"


def test_delete_selfie_keeps_avatar_and_portrait_usable(client, monkeypatch):
    app, c = client
    stub = StubImageStyler()
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: stub)

    resp = _upload(c)
    avatar_id = resp.json()["id"]
    _poll_until_terminal(c, resp.json()["job_id"])
    c.post(f"/api/avatars/{avatar_id}/approve")

    avatar = c.get(f"/api/avatars/{avatar_id}").json()
    selfie_path = Path(avatar["selfie_path"])
    assert selfie_path.exists()

    resp = c.delete(f"/api/avatars/{avatar_id}/selfie")
    assert resp.status_code == 200
    body = resp.json()
    assert body["selfie_path"] is None
    assert body["approved"] is True
    assert body["portrait_path"] is not None
    assert not selfie_path.exists()

    # Still reusable in the library / for rendering.
    listed = c.get("/api/avatars").json()
    assert any(a["id"] == avatar_id for a in listed)

    # But a restyle attempt now fails cleanly (no selfie left).
    restyle_resp = c.post(f"/api/avatars/{avatar_id}/restyle", json={"persona_description": "New look"})
    assert restyle_resp.status_code == 200  # job enqueues fine
    final = _poll_until_terminal(c, restyle_resp.json()["job_id"])
    assert final["status"] == "failed"
    assert "no selfie" in final["error"].lower()


def test_delete_avatar_removes_files(client, monkeypatch):
    app, c = client
    stub = StubImageStyler()
    monkeypatch.setattr(avatar_styling, "make_image_styler", lambda: stub)

    resp = _upload(c)
    avatar_id = resp.json()["id"]
    _poll_until_terminal(c, resp.json()["job_id"])
    avatar = c.get(f"/api/avatars/{avatar_id}").json()
    avatar_dir = Path(avatar["selfie_path"]).parent
    assert avatar_dir.exists()

    delete_resp = c.delete(f"/api/avatars/{avatar_id}")
    assert delete_resp.status_code == 204
    assert not avatar_dir.exists()
    assert c.get(f"/api/avatars/{avatar_id}").status_code == 404


def test_image_styler_conforms_expected_interface():
    styler = ImageStyler(api_key=None, model="gemini-2.5-flash-image")
    with pytest.raises(Exception):
        styler.style(FIXTURE_FACE, "image/jpeg", "Astrologer")
