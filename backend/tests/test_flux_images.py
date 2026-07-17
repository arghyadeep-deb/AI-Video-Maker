"""FluxImages — task-23's corrected FLUX image engine, calling the model's
own public Space via gradio_client (the Inference Providers API-key route
was tried first and found to have no genuine free tier - see flux.py's own
docstring). Tests inject a fake gradio_client.Client via client_factory
(same DI pattern as scene_gen/ltx_public.py's own tests) so nothing here
ever makes a real network call.
"""
import asyncio

import pytest

from app.engines.images.flux import FluxImages, FluxImageUnavailableError


class _FakeClient:
    def __init__(self, image_path: str, exc: Exception | None = None):
        self._image_path = image_path
        self._exc = exc
        self.calls = 0

    def predict(self, **kwargs):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        # /infer's Image output returns the filepath as a plain string, not
        # a dict - a real bug this test would have masked with the wrong
        # shape (found live: "string indices must be integers, not 'str'").
        return (self._image_path, 42)


def test_search_returns_one_candidate_with_the_generated_image_bytes(tmp_path):
    image_path = tmp_path / "generated.jpg"
    image_path.write_bytes(b"fake image bytes")
    fake_client = _FakeClient(str(image_path))
    engine = FluxImages(client_factory=lambda: fake_client)

    candidates = asyncio.run(engine.search("a cat in a library", "9x16", per_page=1))

    assert len(candidates) == 1
    assert candidates[0].source == "flux"
    assert candidates[0].image_bytes == b"fake image bytes"
    assert candidates[0].width == 1024 and candidates[0].height == 1024
    assert fake_client.calls == 1


def test_client_is_cached_across_multiple_searches(tmp_path):
    image_path = tmp_path / "generated.jpg"
    image_path.write_bytes(b"x")
    fake_client = _FakeClient(str(image_path))
    factory_calls = {"n": 0}

    def factory():
        factory_calls["n"] += 1
        return fake_client

    engine = FluxImages(client_factory=factory)
    for _ in range(3):
        asyncio.run(engine.search("prompt", "9x16", per_page=1))

    assert factory_calls["n"] == 1
    assert fake_client.calls == 3


def test_a_client_failure_becomes_flux_image_unavailable_error(tmp_path):
    fake_client = _FakeClient("unused", exc=RuntimeError("402 Payment Required"))
    engine = FluxImages(client_factory=lambda: fake_client)

    with pytest.raises(FluxImageUnavailableError, match="402"):
        asyncio.run(engine.search("prompt", "9x16", per_page=1))


def test_a_call_exceeding_the_timeout_becomes_flux_image_unavailable_error(tmp_path):
    import time

    class _SlowClient:
        def predict(self, **kwargs):
            time.sleep(0.2)
            return ("never-reached", 1)

    engine = FluxImages(timeout_s=0.05, client_factory=lambda: _SlowClient())

    with pytest.raises(FluxImageUnavailableError):
        asyncio.run(engine.search("prompt", "9x16", per_page=1))
