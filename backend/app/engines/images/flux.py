"""FLUX.1-schnell via its own official public Space — task-23-quality-and-ops.md.

Correction, 2026-07-18: the first version of this engine used HF's
"Inference Providers" API-key route (`InferenceClient.text_to_image`). That
looked free in one test call but was actually a one-time trial-credit
bonus - checked directly afterward and FLUX.1-schnell has NO genuine free
`hf-inference` provider at all, only paid third-party ones (nscale, fal-ai,
together, replicate, wavespeed); the credit ran out on the very next call
(real 402 Payment Required, confirmed live). Same dead end as CLIP, which
also has zero provider mappings right now.

The pattern that actually works, proven twice now (first for video via
Lightricks' public Space, same idea here): call the model creators'
own public Gradio Space directly via gradio_client instead of the paid
Inference Providers marketplace - their infrastructure, genuinely free to
call, same accepted third-party-dependency tradeoff as edge-tts's own
"unofficial API, can go down" caveat. Verified live: 7.4s for a real,
well-matched image.
"""
import asyncio
from typing import Callable, Optional

from gradio_client import Client

from app.engines.images.base import StockImageEngine
from app.models.image import ImageCandidate

PUBLIC_SPACE_ID = "black-forest-labs/FLUX.1-schnell"
DEFAULT_TIMEOUT_S = 60.0

# Same style-suffix convention as genai_fallback.py's own STYLE_SUFFIX -
# keeps every scene in one video visually cohesive rather than each
# generated image looking like a different artist did it.
STYLE_SUFFIX = ", cinematic lighting, photorealistic, consistent visual style"

GENERATED_WIDTH = 1024
GENERATED_HEIGHT = 1024


class FluxImageUnavailableError(Exception):
    pass


class FluxImages(StockImageEngine):
    def __init__(
        self,
        hf_token: Optional[str] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client_factory: Optional[Callable[[], Client]] = None,
    ):
        # hf_token here only raises this Space call's own ZeroGPU quota tier
        # (found live: calling anonymously hits the tiny 2-minute
        # unauthenticated bucket and fails immediately with "exceeded your
        # ZeroGPU quota... authenticate for more quota") - it is NOT the
        # paid Inference Providers route this engine already moved away
        # from once (see this file's own docstring).
        self._timeout_s = timeout_s
        self._client_factory = client_factory or (lambda: Client(PUBLIC_SPACE_ID, token=hf_token))
        self._client: Optional[Client] = None

    def _get_client(self) -> Client:
        # Cached across scenes in the same render - each Client() fetches
        # the Space's API schema over the network, wasteful to redo per scene.
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def _call_once(self, prompt: str) -> str:
        client = self._get_client()
        result, _seed = client.predict(
            prompt=prompt,
            seed=0,
            randomize_seed=True,
            width=GENERATED_WIDTH,
            height=GENERATED_HEIGHT,
            num_inference_steps=4,
            api_name="/infer",
        )
        # /infer's Image output returns the filepath directly as a plain
        # string (verified live) - NOT a dict like scene-gen's video output
        # was. Wrongly assumed result["path"] the first time; caught by
        # actually testing on the server, not by re-reading my own code.
        return result

    async def search(
        self, query: str, orientation: str, per_page: int = 1
    ) -> list[ImageCandidate]:
        prompt = f"{query}{STYLE_SUFFIX}"
        try:
            image_path = await asyncio.wait_for(
                asyncio.to_thread(self._call_once, prompt), timeout=self._timeout_s
            )
        except Exception as exc:  # noqa: BLE001 - any Space/network failure falls through
            raise FluxImageUnavailableError(str(exc)) from exc

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        return [
            ImageCandidate(
                source="flux",
                source_id=f"flux:{abs(hash(prompt))}",
                width=GENERATED_WIDTH,
                height=GENERATED_HEIGHT,
                image_bytes=image_bytes,
            )
        ]
