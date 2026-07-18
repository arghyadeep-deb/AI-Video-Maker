"""LTX-2.3 image-to-video via Lightricks' own public ZeroGPU Space —
interim path while `hf-space-scene-gen/` can't be hosted under our own
account (task-23: Hugging Face now requires a PRO subscription to host
ANY new Space, even cpu-basic, and this account is too new for the
30-day free-hosting exception - confirmed live, 2026-07-17).

Upgraded 2026-07-18 (task-23) from `Lightricks/ltx-video-distilled`
(LTX-Video 0.9-era) to `Lightricks/LTX-2-3` (LTX 2.3 Distilled): the
current-generation model, natively trained on vertical video, far less
"animated slideshow" feel. API probed live via the Space's
/gradio_api/info before this rewrite - the endpoint, parameter names,
and return shape below match what the Space actually serves, not an
assumption carried over from the old Space.

Two deliberate consequences of the new model:

- **The generated clip contains an audio track** (LTX-2 generates
  synchronized audio natively). We do NOT use it: the one-audio-clock
  invariant means narration rules the timeline. No stripping step is
  needed - `build_kenburns_filter_complex` only ever references clip
  inputs as `[N:v]` and the final mux maps the narration mix alone, so
  ffmpeg drops clip audio by construction (verified against
  engines/ffmpeg/kenburns.py before relying on it).
- **Dimensions are free-form Numbers on this Space** (the old Space's
  704px slider clamp is gone). We preserve the requested aspect ratio,
  cap the long side at MAX_LONG_SIDE to stay well inside ZeroGPU's 120s
  per-call ceiling, and snap both dims down to multiples of 32 (the
  model's stride) - e.g. a 1080x1920 request becomes 704x1280, a real
  resolution upgrade over the old Space's square-ish 704 clamp.

This deliberately calls a third party's public demo directly, which is
NOT this project's usual rule (`sadtalker_zerogpu.py`'s own docstring:
"not a third-party demo Space") - an explicit, accepted interim tradeoff
(shared with all its public users, not under our control, could change
without notice) rather than shipping nothing. Same class of risk this
project already accepts elsewhere for edge-tts's own "unofficial API,
can go down" caveat. Switch to `hf-space-scene-gen/` (already built) the
moment our own account can host it - 2026-08-16, or sooner via a
community-grant approval.

`gradio_client.Client.predict` is a blocking call - run via
`asyncio.to_thread` so it never blocks the job worker's event loop for
its real-world duration (found live during task-23: forgetting this
would starve every other concurrent request the whole time).
"""
import asyncio
from pathlib import Path
from typing import Callable, Optional

from gradio_client import Client, handle_file

PUBLIC_SPACE_ID = "Lightricks/LTX-2-3"
# Cap the long side to keep per-call wall time comfortably inside
# ZeroGPU's hard 120s ceiling; snap to the model's 32px stride.
MAX_LONG_SIDE = 1280
DIM_STRIDE = 32
MIN_DIM = 256
# The Space's duration slider bounds (probed from /gradio_api/info).
MIN_DURATION_S = 1.0
MAX_DURATION_S = 10.0
DEFAULT_TIMEOUT_S = 90.0


class LTXPublicSpaceError(Exception):
    """Any failure calling the public Space - network, queue timeout,
    Space unavailable, or a malformed response. Callers fall back to the
    next tier (home worker, then Ken Burns), never propagate raw."""


def fit_dims(width: int, height: int) -> tuple[int, int]:
    """Aspect-preserving fit: cap the long side at MAX_LONG_SIDE, snap
    both dims down to the model stride, floor at MIN_DIM."""
    long_side = max(width, height)
    scale = min(1.0, MAX_LONG_SIDE / long_side)
    def _snap(v: float) -> int:
        return max(MIN_DIM, int(v * scale) // DIM_STRIDE * DIM_STRIDE)
    return _snap(width), _snap(height)


class LTXPublicSpaceEngine:
    def __init__(
        self,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client_factory: Optional[Callable[[], Client]] = None,
    ):
        self._timeout_s = timeout_s
        self._client_factory = client_factory or (lambda: Client(PUBLIC_SPACE_ID))
        self._client: Optional[Client] = None

    def _get_client(self) -> Client:
        # Cached across scenes in the same render - each Client() fetches
        # the Space's API schema over the network, wasteful to redo per scene.
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def _call_once(self, image_path: str, prompt: str, duration_s: float, width: int, height: int) -> str:
        client = self._get_client()
        w, h = fit_dims(width, height)
        result = client.predict(
            input_image=handle_file(image_path),
            prompt=prompt,
            duration=min(MAX_DURATION_S, max(MIN_DURATION_S, duration_s)),
            enhance_prompt=False,
            seed=42,
            randomize_seed=True,
            height=h,
            width=w,
            api_name="/generate_video",
        )
        video_info, _seed = result
        # The probed return type is `filepath` (a plain str), but older
        # gradio versions wrap Video outputs in a dict - accept both so a
        # Space-side gradio upgrade doesn't turn into a silent breakage.
        if isinstance(video_info, dict):
            path = video_info.get("video") or video_info.get("path")
            if not path:
                raise LTXPublicSpaceError(f"malformed video response: {video_info!r}")
            return path
        return video_info

    async def render(
        self, image_path: str, prompt: str, duration_s: float, width: int, height: int, output_path: str
    ) -> Path:
        try:
            result_path = await asyncio.wait_for(
                asyncio.to_thread(self._call_once, image_path, prompt, duration_s, width, height),
                timeout=self._timeout_s,
            )
        except Exception as exc:  # noqa: BLE001 - any Space/network failure falls back
            raise LTXPublicSpaceError(str(exc)) from exc
        out_path = Path(output_path)
        out_path.write_bytes(Path(result_path).read_bytes())
        return out_path
