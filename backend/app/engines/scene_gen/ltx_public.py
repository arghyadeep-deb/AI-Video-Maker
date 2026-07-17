"""LTX-Video image-to-video via Lightricks' own public ZeroGPU Space —
interim path while `hf-space-scene-gen/` can't be hosted under our own
account (task-23: Hugging Face now requires a PRO subscription to host
ANY new Space, even cpu-basic, and this account is too new for the
30-day free-hosting exception - confirmed live, 2026-07-17).

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
its ~15-20s real-world duration (found live during task-23: forgetting
this would starve every other concurrent request the whole time).
"""
import asyncio
from pathlib import Path
from typing import Callable, Optional

from gradio_client import Client, handle_file

PUBLIC_SPACE_ID = "Lightricks/ltx-video-distilled"
# The Space's own UI caps width/height at 704 - passing anything larger
# gets silently clamped by Gradio's own slider bounds, so match it here
# rather than let a silent mismatch confuse duration/frame-count math.
MAX_DIM = 704
DEFAULT_TIMEOUT_S = 90.0


class LTXPublicSpaceError(Exception):
    """Any failure calling the public Space - network, queue timeout,
    Space unavailable, or a malformed response. Callers fall back to the
    next tier (home worker, then Ken Burns), never propagate raw."""


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
        result = client.predict(
            prompt=prompt,
            negative_prompt="worst quality, inconsistent motion, blurry, jittery, distorted",
            input_image_filepath=handle_file(image_path),
            input_video_filepath=None,
            height_ui=min(height, MAX_DIM),
            width_ui=min(width, MAX_DIM),
            mode="image-to-video",
            duration_ui=duration_s,
            ui_frames_to_use=9,
            seed_ui=42,
            randomize_seed=True,
            ui_guidance_scale=1,
            improve_texture_flag=True,
            api_name="/image_to_video",
        )
        video_info, _seed = result
        return video_info["video"]

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
