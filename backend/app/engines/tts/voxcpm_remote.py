"""VoxCPM on a Hugging Face ZeroGPU Space — specs/04-tasks/task-18-voice-cloning-voxcpm.md's
"Optional 'HD voice' | VoxCPM full generative cloning | ZeroGPU slot".

Calls the owner's own deployed Space (hf-space/, wrapping VoxCPM with
`clone_speak(text, ref_wav) -> wav` and `design_speak(text, description) ->
wav` contracts) via gradio_client - same shape as
app/engines/talking_head/sadtalker_zerogpu.py's SadTalker client, sharing
the SAME global GPU-seconds ledger (app/quota/gpu_budget.py) rather than a
separate budget, per specs/01-requirements/10-hosting-accounts-quotas.md's
locked "one shared ZeroGPU quota across GPU-consuming features" model.

VoxCPM has no native word-boundary events (it's a generative model, not
edge-tts) - word timings come from forced alignment against the known
script text (app/services/forced_alignment.py), never free ASR of unknown
text, per the project's own hard invariant.
"""
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

from gradio_client import Client, handle_file

from app.engines.tts.base import SpeechResult, TTSEngine
from app.quota import gpu_budget
from app.services.forced_alignment import forced_align

DEFAULT_TIMEOUT_S = 120
DEFAULT_ESTIMATE_SECONDS = 30.0

# Same reasoning as sadtalker_zerogpu.py's own pattern: distinguishes a
# rejected-before-running quota error (refundable) from a genuine mid-render
# crash (GPU time already spent, not refunded).
QUOTA_ERROR_PATTERN = re.compile(r"(gpu quota|exceeded your gpu|zerogpu.*quota)", re.IGNORECASE)


class VoxCPMEngineError(Exception):
    pass


class VoxCPMQuotaExhaustedError(VoxCPMEngineError):
    pass


class VoxCPMRemoteEngine(TTSEngine):
    """`design_wav_path=None` -> clone_speak (voice-cloned from a reference
    sample); otherwise -> design_speak (a described persona voice, no
    reference sample needed)."""

    def __init__(
        self,
        space_id: Optional[str],
        hf_token: Optional[str],
        conn: sqlite3.Connection,
        daily_limit_seconds: float,
        reference_wav_path: Optional[Path] = None,
        persona_description: Optional[str] = None,
        estimate_seconds: float = DEFAULT_ESTIMATE_SECONDS,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client_factory=None,
    ):
        if not reference_wav_path and not persona_description:
            raise ValueError("VoxCPMRemoteEngine needs either reference_wav_path or persona_description")
        self._space_id = space_id
        self._hf_token = hf_token
        self._conn = conn
        self._daily_limit_seconds = daily_limit_seconds
        self._reference_wav_path = reference_wav_path
        self._persona_description = persona_description
        self._estimate_seconds = estimate_seconds
        self._timeout_s = timeout_s
        self._client_factory = client_factory or (lambda: Client(space_id, token=hf_token))

    def _call_once(self, text: str) -> str:
        client = self._client_factory()
        if self._reference_wav_path is not None:
            return client.predict(text, handle_file(str(self._reference_wav_path)), api_name="/clone_speak")
        return client.predict(text, self._persona_description, api_name="/design_speak")

    async def speak(
        self, text: str, voice: str, out_path: Path, rate: Optional[str] = None
    ) -> SpeechResult:
        if not self._space_id:
            raise VoxCPMEngineError("VOXCPM_SPACE_ID is not configured")

        if not gpu_budget.has_budget(self._conn, self._daily_limit_seconds, self._estimate_seconds):
            raise VoxCPMQuotaExhaustedError("Daily ZeroGPU budget exhausted")

        gpu_budget.record_usage(self._conn, self._estimate_seconds)

        last_error: Optional[Exception] = None
        for attempt in range(2):  # one retry, matching SadTalker's own client
            try:
                start = time.monotonic()
                result_path = self._call_once(text)
                elapsed = time.monotonic() - start
                gpu_budget.record_usage(self._conn, max(0.0, elapsed - self._estimate_seconds))

                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(Path(result_path).read_bytes())
                timings = forced_align(out_path, text)
                return SpeechResult(audio_path=out_path, timings=timings)
            except Exception as exc:  # noqa: BLE001 - any Space/network/alignment failure
                last_error = exc
                if QUOTA_ERROR_PATTERN.search(str(exc)):
                    gpu_budget.refund_usage(self._conn, self._estimate_seconds)
                    raise VoxCPMQuotaExhaustedError(str(exc)) from exc

        raise VoxCPMEngineError(str(last_error))
