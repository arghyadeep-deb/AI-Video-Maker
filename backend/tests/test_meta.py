from fastapi.testclient import TestClient

from app.main import create_app


def _client(monkeypatch, tmp_path, **env):
    # setenv("") rather than delenv: with a real repo-root .env now present
    # (live keys since 2026-07-11), delenv would let pydantic-settings fall
    # back to the dotenv FILE - an empty env var wins over it and stays
    # falsy for the health endpoint's bool() checks.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("PEXELS_API_KEY", "")
    monkeypatch.setenv("PIXABAY_API_KEY", "")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))

    from app.core.config import get_settings

    get_settings.cache_clear()
    return TestClient(create_app())


def test_health_shape_without_keys(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        resp = client.get("/api/meta/health")
        assert resp.status_code == 200
        body = resp.json()

        assert body["keys_configured"] == {
            "gemini": False,
            "pexels": False,
            "pixabay": False,
        }
        assert body["db_migrated"] is True
        assert body["schema_version"] > 0
        assert "present" in body["ffmpeg"]
        assert isinstance(body["cuda_available"], bool)


def test_health_shape_with_keys(monkeypatch, tmp_path):
    with _client(
        monkeypatch,
        tmp_path,
        GEMINI_API_KEY="gk",
        PEXELS_API_KEY="pk",
        PIXABAY_API_KEY="pb",
    ) as client:
        resp = client.get("/api/meta/health")
        body = resp.json()
        assert body["keys_configured"] == {
            "gemini": True,
            "pexels": True,
            "pixabay": True,
        }


def test_health_detects_missing_ffmpeg_honestly(monkeypatch, tmp_path):
    # This dev machine has no ffmpeg on PATH — health must report that
    # honestly rather than assuming it's present.
    monkeypatch.setenv("PATH", str(tmp_path))
    with _client(monkeypatch, tmp_path) as client:
        resp = client.get("/api/meta/health")
        body = resp.json()
        assert body["ffmpeg"]["present"] is False
        assert body["ffmpeg"]["version"] is None
        assert body["subtitle_filters_available"] is False


def test_voices_endpoint_returns_locked_table(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        resp = client.get("/api/meta/voices")
        assert resp.status_code == 200
        assert resp.json() == {
            "hi": {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"},
            "en": {"female": "en-IN-NeerjaNeural", "male": "en-IN-PrabhatNeural"},
            "en-US": {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"},
        }


def test_tier_endpoint_is_public_and_honest_about_no_worker(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        resp = client.get("/api/meta/tier")
        assert resp.status_code == 200
        body = resp.json()
        assert body["worker_online"] is False
        assert body["sadtalker_configured"] is False
        assert body["active_tier"] == "cpu"
        assert body["label"] == "Photo mode only"


def test_music_moods_lists_the_real_bundled_moods(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        resp = client.get("/api/meta/music/moods")
        assert resp.status_code == 200
        assert set(resp.json()) == {"calm", "upbeat", "mystical", "corporate"}


def test_music_preview_returns_a_playable_clip(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        resp = client.get("/api/meta/music/preview/calm")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
        assert len(resp.content) > 0


def test_music_preview_404s_for_an_unknown_mood(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        resp = client.get("/api/meta/music/preview/nonexistent")
        assert resp.status_code == 404
