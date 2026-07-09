"""API-level tests for personal voice enrollment - specs/04-tasks/task-18-voice-cloning-voxcpm.md.

Uses real OpenVoice inference (fast enough on CPU, per this session's
established pattern of not mocking away model inference when feasible) and
a real edge-tts-synthesized sample as a stand-in for a browser recording
(this dev environment has network access to the free edge-tts service,
confirmed by prior tasks' own live smoke tests).
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engines.tts.openvoice import is_available
from app.main import create_app
from tests.conftest import authenticate

pytestmark = pytest.mark.skipif(not is_available(), reason="OpenVoice checkpoint not available")


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


async def _real_sample_bytes(tmp_path) -> bytes:
    """A real speech sample via edge-tts, well clear of the validator's
    15s-of-*detected*-speech floor (natural inter-sentence pauses in the
    synthesized audio get excluded from the detected-speech measurement,
    so the raw clip needs real margin above 15s, not just barely over it -
    found by actually running this at a tighter margin first). Skips (not
    fails) if edge-tts is unreachable, same pattern as
    test_openvoice_engine.py/test_voxcpm_remote.py."""
    from app.engines.tts.edge import EdgeTTSEngine

    text = " ".join(["Hello, this is my voice, and I am reading a short passage for enrollment."] * 12)
    out_path = tmp_path / "sample.mp3"
    try:
        await EdgeTTSEngine().speak(text, "en-US-AriaNeural", out_path)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"edge-tts unreachable in this environment: {exc}")
    return out_path.read_bytes()


def test_get_passage_returns_the_real_bundled_text(client):
    _, c = client
    resp = c.get("/api/voices/passage/en")
    assert resp.status_code == 200
    assert len(resp.json()["text"]) > 0

    resp_hi = c.get("/api/voices/passage/hi")
    assert resp_hi.status_code == 200
    assert len(resp_hi.json()["text"]) > 0


def test_get_passage_404s_for_unknown_language(client):
    _, c = client
    resp = c.get("/api/voices/passage/fr")
    assert resp.status_code == 404


def test_enroll_requires_consent(client):
    _, c = client
    resp = c.post(
        "/api/voices/enroll",
        files={"sample": ("sample.mp3", b"fake-bytes-not-checked-first", "audio/mpeg")},
        data={"language": "en", "consent": "false"},
    )
    assert resp.status_code == 400
    assert "consent" in resp.json()["error"]["message"].lower()


async def test_enroll_rejects_a_too_short_recording(client, tmp_path):
    """A single short line clearly under the 15s floor - doesn't need a
    real network call, this just proves the validation wiring rejects
    honestly rather than silently accepting anything."""
    import subprocess

    short_path = tmp_path / "short.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=200:duration=3", str(short_path)],
        check=True, capture_output=True, timeout=15,
    )
    _, c = client
    resp = c.post(
        "/api/voices/enroll",
        files={"sample": ("sample.wav", short_path.read_bytes(), "audio/wav")},
        data={"language": "en", "consent": "true"},
    )
    assert resp.status_code == 400
    assert "least" in resp.json()["error"]["message"].lower() or "least" in (resp.json()["error"].get("hint") or "").lower()


async def test_enroll_end_to_end_with_real_speech(client, tmp_path):
    app, c = client
    sample_bytes = await _real_sample_bytes(tmp_path)

    resp = c.post(
        "/api/voices/enroll",
        files={"sample": ("sample.mp3", sample_bytes, "audio/mpeg")},
        data={"language": "en", "consent": "true"},
    )
    assert resp.status_code == 201, resp.text
    profile = resp.json()
    assert profile["kind"] == "cloned"
    assert profile["consented"] is True
    assert profile["base_voice"] in {"en-IN-NeerjaNeural", "en-IN-PrabhatNeural"}

    list_resp = c.get("/api/voices")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    preview_resp = c.get(f"/api/voices/{profile['id']}/preview")
    assert preview_resp.status_code == 200, preview_resp.text
    assert preview_resp.headers["content-type"] == "audio/mpeg"
    assert len(preview_resp.content) > 0


async def test_re_enrolling_replaces_the_existing_cloned_profile(client, tmp_path):
    app, c = client
    sample_bytes = await _real_sample_bytes(tmp_path)

    first = c.post(
        "/api/voices/enroll",
        files={"sample": ("sample.mp3", sample_bytes, "audio/mpeg")},
        data={"language": "en", "consent": "true"},
    ).json()

    second = c.post(
        "/api/voices/enroll",
        files={"sample": ("sample.mp3", sample_bytes, "audio/mpeg")},
        data={"language": "en", "consent": "true"},
    ).json()

    assert second["id"] != first["id"]
    profiles = c.get("/api/voices").json()
    assert len(profiles) == 1
    assert profiles[0]["id"] == second["id"]


def test_design_voice_fails_honestly_without_a_deployed_space(client):
    _, c = client
    resp = c.post("/api/voices/design", json={"description": "wise old astrologer"})
    assert resp.status_code == 400
    assert "available" in resp.json()["error"]["message"].lower()


async def test_delete_removes_row_and_files(client, tmp_path):
    app, c = client
    sample_bytes = await _real_sample_bytes(tmp_path)
    profile = c.post(
        "/api/voices/enroll",
        files={"sample": ("sample.mp3", sample_bytes, "audio/mpeg")},
        data={"language": "en", "consent": "true"},
    ).json()

    settings = get_settings()
    from app.api.voices import _profile_dir
    from tests.conftest import DEV_USER_ID

    profile_dir = _profile_dir(settings, DEV_USER_ID, profile["id"])
    assert profile_dir.exists()

    resp = c.delete(f"/api/voices/{profile['id']}")
    assert resp.status_code == 204
    assert not profile_dir.exists()
    assert c.get("/api/voices").json() == []
