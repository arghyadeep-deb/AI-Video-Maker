"""LTXPublicSpaceEngine — task-23's interim public-Space tier for
Generated Footage. Tests inject a fake gradio_client.Client via
client_factory (same DI pattern as sadtalker_zerogpu.py's own tests) so
nothing here ever makes a real network call.
"""
import asyncio

import pytest

from app.engines.scene_gen.ltx_public import LTXPublicSpaceEngine, LTXPublicSpaceError


class _FakeClient:
    def __init__(self, video_path: str, exc: Exception | None = None):
        self._video_path = video_path
        self._exc = exc
        self.calls = 0

    def predict(self, **kwargs):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return ({"video": self._video_path, "subtitles": None}, 42)


def test_render_writes_the_returned_video_to_output_path(tmp_path):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"fake mp4 bytes")
    fake_client = _FakeClient(str(source_video))
    engine = LTXPublicSpaceEngine(client_factory=lambda: fake_client)

    output_path = tmp_path / "clip.mp4"
    image_path = tmp_path / "scene.jpg"
    image_path.write_bytes(b"jpg")

    result = asyncio.run(
        engine.render(str(image_path), "a robot in a garden", 5.0, 1080, 1920, str(output_path))
    )

    assert result == output_path
    assert output_path.read_bytes() == b"fake mp4 bytes"
    assert fake_client.calls == 1


def test_client_is_cached_across_multiple_renders(tmp_path):
    """Client() re-fetches the Space's API schema over the network - must
    only happen once per engine instance, not once per scene."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"x")
    fake_client = _FakeClient(str(source_video))
    factory_calls = {"n": 0}

    def factory():
        factory_calls["n"] += 1
        return fake_client

    engine = LTXPublicSpaceEngine(client_factory=factory)
    image_path = tmp_path / "scene.jpg"
    image_path.write_bytes(b"jpg")

    for i in range(3):
        asyncio.run(
            engine.render(str(image_path), "prompt", 5.0, 1080, 1920, str(tmp_path / f"out{i}.mp4"))
        )

    assert factory_calls["n"] == 1
    assert fake_client.calls == 3


def test_a_client_failure_becomes_ltx_public_space_error(tmp_path):
    fake_client = _FakeClient("unused", exc=RuntimeError("Space is sleeping"))
    engine = LTXPublicSpaceEngine(client_factory=lambda: fake_client)
    image_path = tmp_path / "scene.jpg"
    image_path.write_bytes(b"jpg")

    with pytest.raises(LTXPublicSpaceError, match="Space is sleeping"):
        asyncio.run(
            engine.render(str(image_path), "prompt", 5.0, 1080, 1920, str(tmp_path / "out.mp4"))
        )


def test_a_call_exceeding_the_timeout_becomes_ltx_public_space_error(tmp_path):
    import time

    class _SlowClient:
        def predict(self, **kwargs):
            time.sleep(0.2)
            return ({"video": "never-reached", "subtitles": None}, 1)

    engine = LTXPublicSpaceEngine(timeout_s=0.05, client_factory=lambda: _SlowClient())
    image_path = tmp_path / "scene.jpg"
    image_path.write_bytes(b"jpg")

    with pytest.raises(LTXPublicSpaceError):
        asyncio.run(
            engine.render(str(image_path), "prompt", 5.0, 1080, 1920, str(tmp_path / "out.mp4"))
        )
