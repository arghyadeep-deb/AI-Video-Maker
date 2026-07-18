"""LTXPublicSpaceEngine — task-23's interim public-Space tier for
Generated Footage, upgraded 2026-07-18 to the Lightricks/LTX-2-3 Space.
Tests inject a fake gradio_client.Client via client_factory (same DI
pattern as sadtalker_zerogpu.py's own tests) so nothing here ever makes
a real network call.
"""
import asyncio

import pytest

from app.engines.scene_gen.ltx_public import (
    LTXPublicSpaceEngine,
    LTXPublicSpaceError,
    fit_dims,
)


class _FakeClient:
    """Mimics the LTX-2-3 Space's probed return shape: (filepath, seed)."""

    def __init__(self, video_path: str, exc: Exception | None = None, dict_shaped: bool = False):
        self._video_path = video_path
        self._exc = exc
        self._dict_shaped = dict_shaped
        self.calls = 0
        self.last_kwargs: dict | None = None

    def predict(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._exc is not None:
            raise self._exc
        if self._dict_shaped:
            return ({"video": self._video_path, "subtitles": None}, 42)
        return (self._video_path, 42)


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


def test_call_targets_the_ltx23_generate_video_endpoint(tmp_path):
    """The 2026-07-18 Space swap: endpoint + parameter names must match
    what Lightricks/LTX-2-3 actually serves (probed via /gradio_api/info),
    with vertical 1080x1920 fitted to 704x1280 (32px stride, 1280 cap)."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"x")
    fake_client = _FakeClient(str(source_video))
    engine = LTXPublicSpaceEngine(client_factory=lambda: fake_client)
    image_path = tmp_path / "scene.jpg"
    image_path.write_bytes(b"jpg")

    asyncio.run(
        engine.render(str(image_path), "prompt", 5.0, 1080, 1920, str(tmp_path / "out.mp4"))
    )

    kwargs = fake_client.last_kwargs
    assert kwargs["api_name"] == "/generate_video"
    assert kwargs["prompt"] == "prompt"
    assert kwargs["duration"] == 5.0
    assert (kwargs["width"], kwargs["height"]) == (704, 1280)


def test_duration_is_clamped_to_the_space_slider_bounds(tmp_path):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"x")
    fake_client = _FakeClient(str(source_video))
    engine = LTXPublicSpaceEngine(client_factory=lambda: fake_client)
    image_path = tmp_path / "scene.jpg"
    image_path.write_bytes(b"jpg")

    asyncio.run(
        engine.render(str(image_path), "prompt", 25.0, 1080, 1920, str(tmp_path / "out.mp4"))
    )
    assert fake_client.last_kwargs["duration"] == 10.0

    asyncio.run(
        engine.render(str(image_path), "prompt", 0.2, 1080, 1920, str(tmp_path / "out2.mp4"))
    )
    assert fake_client.last_kwargs["duration"] == 1.0


def test_a_dict_shaped_video_response_still_works(tmp_path):
    """Older gradio versions wrap Video outputs in a dict - a Space-side
    gradio upgrade must not silently break the tier."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"dict shaped")
    fake_client = _FakeClient(str(source_video), dict_shaped=True)
    engine = LTXPublicSpaceEngine(client_factory=lambda: fake_client)
    image_path = tmp_path / "scene.jpg"
    image_path.write_bytes(b"jpg")

    output_path = tmp_path / "out.mp4"
    asyncio.run(engine.render(str(image_path), "prompt", 5.0, 1080, 1920, str(output_path)))
    assert output_path.read_bytes() == b"dict shaped"


def test_fit_dims_preserves_aspect_caps_and_snaps():
    # Vertical 9:16 request: long side capped at 1280, both snapped to /32.
    assert fit_dims(1080, 1920) == (704, 1280)
    # Landscape mirror.
    assert fit_dims(1920, 1080) == (1280, 704)
    # Already small: untouched except stride snap.
    assert fit_dims(704, 704) == (704, 704)
    # Never below the floor.
    assert fit_dims(100, 4000) == (256, 1280)


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
            return ("never-reached", 1)

    engine = LTXPublicSpaceEngine(timeout_s=0.05, client_factory=lambda: _SlowClient())
    image_path = tmp_path / "scene.jpg"
    image_path.write_bytes(b"jpg")

    with pytest.raises(LTXPublicSpaceError):
        asyncio.run(
            engine.render(str(image_path), "prompt", 5.0, 1080, 1920, str(tmp_path / "out.mp4"))
        )
