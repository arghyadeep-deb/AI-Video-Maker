"""SadTalker on a Hugging Face ZeroGPU Space — specs/03-design/04-mode-a-pipeline.md.

Calls the owner's own deployed Space (hf-space/, this project's Gradio app
wrapping SadTalker with a `render(portrait, wav) -> mp4` contract) via
`gradio_client`, not a third-party demo Space.

Implementation notes locked in specs/04-tasks/task-11-talking-head.md:
- "--still flag, WAV 16kHz, portrait 1024x1024"  (enforced by the caller/
  upstream pipeline stages, not re-validated here)
- "Space call timeout + retry-once"
- "on ZeroGPU quota error -> fall back to Wav2Lip and refund the slot"
"""
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

from gradio_client import Client, handle_file

from app.engines.talking_head.base import TalkingHeadEngine, TalkingHeadEngineError, TalkingHeadResult
from app.quota import gpu_budget

DEFAULT_TIMEOUT_S = 180
DEFAULT_ESTIMATE_SECONDS = 60.0

# ZeroGPU's own runtime raises errors containing phrasing like this when an
# account's daily GPU-second budget is spent - matched case-insensitively so
# a rejected (never actually run) call gets refunded, while a call that
# genuinely crashed mid-render (GPU time already spent) does not.
QUOTA_ERROR_PATTERN = re.compile(r"(gpu quota|exceeded your gpu|zerogpu.*quota)", re.IGNORECASE)


class ZeroGpuQuotaExhaustedError(TalkingHeadEngineError):
    pass


class SadTalkerZeroGPUEngine(TalkingHeadEngine):
    def __init__(
        self,
        space_id: Optional[str],
        hf_token: Optional[str],
        conn: sqlite3.Connection,
        daily_limit_seconds: float,
        estimate_seconds: float = DEFAULT_ESTIMATE_SECONDS,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client_factory=None,
    ):
        self._space_id = space_id
        self._hf_token = hf_token
        self._conn = conn
        self._daily_limit_seconds = daily_limit_seconds
        self._estimate_seconds = estimate_seconds
        self._timeout_s = timeout_s
        self._client_factory = client_factory or (lambda: Client(space_id, token=hf_token))

    def _call_once(self, portrait_path: str, wav_path: str) -> str:
        client = self._client_factory()
        return client.predict(
            handle_file(portrait_path), handle_file(wav_path), api_name="/render"
        )

    async def render(self, portrait_path: str, wav_path: str, output_path: str) -> TalkingHeadResult:
        if not self._space_id:
            raise TalkingHeadEngineError("SADTALKER_SPACE_ID is not configured")

        if not gpu_budget.has_budget(self._conn, self._daily_limit_seconds, self._estimate_seconds):
            raise ZeroGpuQuotaExhaustedError("Daily ZeroGPU budget exhausted")

        gpu_budget.record_usage(self._conn, self._estimate_seconds)

        last_error: Optional[Exception] = None
        for attempt in range(2):  # one retry, per the task's Implementation notes
            try:
                start = time.monotonic()
                result_path = self._call_once(portrait_path, wav_path)
                elapsed = time.monotonic() - start
                # True up the pre-charged estimate with the real elapsed time.
                gpu_budget.record_usage(self._conn, max(0.0, elapsed - self._estimate_seconds))
                Path(output_path).write_bytes(Path(result_path).read_bytes())
                return TalkingHeadResult(video_path=output_path, engine="sadtalker")
            except Exception as exc:  # noqa: BLE001 - any Space/network failure
                last_error = exc
                if QUOTA_ERROR_PATTERN.search(str(exc)):
                    gpu_budget.refund_usage(self._conn, self._estimate_seconds)
                    raise ZeroGpuQuotaExhaustedError(str(exc)) from exc
                # Non-quota failure - keep the charge (GPU time may well have
                # been spent) and retry once before giving up.

        raise TalkingHeadEngineError(str(last_error))
