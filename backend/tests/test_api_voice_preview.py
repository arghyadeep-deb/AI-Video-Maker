import pytest
from fastapi.testclient import TestClient

from app.api.meta import get_tts_engine
from app.core.config import get_settings
from app.engines.tts.fake import FakeTTSEngine
from app.main import create_app
from tests.conftest import authenticate


class CountingFakeTTS(FakeTTSEngine):
    def __init__(self):
        self.calls = 0

    async def speak(self, *args, **kwargs):
        self.calls += 1
        return await super().speak(*args, **kwargs)


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


def test_preview_unknown_voice_returns_404(client):
    _, c = client
    resp = c.get("/api/meta/voices/not-a-real-voice/preview")
    assert resp.status_code == 404


def test_preview_generates_and_caches(client):
    app, c = client
    stub = CountingFakeTTS()
    app.dependency_overrides[get_tts_engine] = lambda: stub

    resp1 = c.get("/api/meta/voices/hi-IN-SwaraNeural/preview")
    assert resp1.status_code == 200, resp1.text
    assert resp1.headers["content-type"] == "audio/mpeg"
    assert stub.calls == 1

    resp2 = c.get("/api/meta/voices/hi-IN-SwaraNeural/preview")
    assert resp2.status_code == 200
    assert stub.calls == 1  # second call hit the cache on disk, not the engine


def test_preview_works_for_every_pinned_voice(client):
    app, c = client
    stub = CountingFakeTTS()
    app.dependency_overrides[get_tts_engine] = lambda: stub

    settings = get_settings()
    voice_ids = [v for pair in settings.voice_table.values() for v in pair.values()]
    for voice_id in voice_ids:
        resp = c.get(f"/api/meta/voices/{voice_id}/preview")
        assert resp.status_code == 200, (voice_id, resp.text)
    assert stub.calls == len(voice_ids)
