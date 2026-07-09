import httpx
import pytest

from app.engines.images.genai_fallback import GenaiFallbackImages, GenaiImageUnavailableError
from app.engines.images.pexels import PexelsImages, PexelsUnavailableError
from app.engines.images.pixabay import PixabayImages, PixabayUnavailableError


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response=None, raise_exc=None, **kwargs):
        self._response = response
        self._raise_exc = raise_exc
        self.requested_url = None
        self.requested_params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        self.requested_url = url
        self.requested_params = params
        if self._raise_exc:
            raise self._raise_exc
        return self._response


class TestPexelsImages:
    async def test_no_api_key_returns_empty_without_network_call(self, monkeypatch):
        def boom(*a, **kw):
            raise AssertionError("should never make an HTTP call without a key")

        monkeypatch.setattr(httpx, "AsyncClient", boom)
        engine = PexelsImages(api_key=None)
        result = await engine.search("sunrise", "9x16")
        assert result == []

    async def test_maps_response_into_candidates(self, monkeypatch):
        fake_response = _FakeResponse(
            {
                "photos": [
                    {
                        "id": 42,
                        "width": 1920,
                        "height": 1200,
                        "src": {"original": "https://images.pexels.com/42.jpg"},
                        "photographer": "Jane Doe",
                        "photographer_url": "https://pexels.com/@jane",
                    }
                ]
            }
        )
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(response=fake_response))

        engine = PexelsImages(api_key="fake-key")
        result = await engine.search("sunrise", "9x16")

        assert len(result) == 1
        assert result[0].source == "pexels"
        assert result[0].source_id == "42"
        assert result[0].url == "https://images.pexels.com/42.jpg"
        assert result[0].photographer == "Jane Doe"

    async def test_transport_error_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kw: _FakeAsyncClient(raise_exc=httpx.ConnectError("down")),
        )
        engine = PexelsImages(api_key="fake-key")
        with pytest.raises(PexelsUnavailableError):
            await engine.search("sunrise", "9x16")


class TestPixabayImages:
    async def test_no_api_key_returns_empty_without_network_call(self, monkeypatch):
        def boom(*a, **kw):
            raise AssertionError("should never make an HTTP call without a key")

        monkeypatch.setattr(httpx, "AsyncClient", boom)
        engine = PixabayImages(api_key=None)
        result = await engine.search("sunrise", "9x16")
        assert result == []

    async def test_maps_response_into_candidates(self, monkeypatch):
        fake_response = _FakeResponse(
            {
                "hits": [
                    {
                        "id": 7,
                        "imageWidth": 1920,
                        "imageHeight": 1200,
                        "largeImageURL": "https://pixabay.com/7.jpg",
                        "user": "someone",
                        "user_id": 99,
                    }
                ]
            }
        )
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(response=fake_response))

        engine = PixabayImages(api_key="fake-key")
        result = await engine.search("sunrise", "9x16")

        assert len(result) == 1
        assert result[0].source == "pixabay"
        assert result[0].photographer_url == "https://pixabay.com/users/someone-99/"

    async def test_transport_error_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kw: _FakeAsyncClient(raise_exc=httpx.ConnectError("down")),
        )
        engine = PixabayImages(api_key="fake-key")
        with pytest.raises(PixabayUnavailableError):
            await engine.search("sunrise", "9x16")


class TestGenaiFallbackImages:
    async def test_no_api_key_raises_unavailable(self):
        engine = GenaiFallbackImages(api_key=None, model="gemini-2.5-flash-image")
        with pytest.raises(GenaiImageUnavailableError):
            await engine.search("sunrise", "9x16")
