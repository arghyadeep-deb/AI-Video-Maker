"""Engine selection + fallback orchestration for Mode A rendering —
specs/03-design/04-mode-a-pipeline.md's engine-selection rules and
specs/03-design/11-gpu-worker.md's three-tier routing (task-20a):

    HD requested -> home worker (plentiful, while the owner's PC is online)
                 -> ZeroGPU Space (rationed, budget-gated)
                 -> Wav2Lip CPU  (always available)

Every tier's failure is an honest degrade, not a job failure: the home
worker vanishing mid-render (PC slept — a normal event) and ZeroGPU quota
exhaustion both fall through silently to the next tier; the engine actually
used is recorded in jobs.engine_notes by the pipeline.
"""
from typing import Optional

from app.engines.talking_head.base import TalkingHeadEngine, TalkingHeadResult
from app.engines.talking_head.sadtalker_zerogpu import ZeroGpuQuotaExhaustedError
from app.jobs.gpu_router import GpuTaskFailed, HomeWorkerUnavailable


async def render_with_fallback(
    hd_requested: bool,
    sadtalker_engine: Optional[TalkingHeadEngine],
    wav2lip_engine: TalkingHeadEngine,
    portrait_path: str,
    wav_path: str,
    output_path: str,
    home_engine: Optional[TalkingHeadEngine] = None,
) -> TalkingHeadResult:
    if hd_requested and home_engine is not None:
        try:
            return await home_engine.render(portrait_path, wav_path, output_path)
        except (HomeWorkerUnavailable, GpuTaskFailed):
            pass  # PC offline/slept/crashed - ZeroGPU or Wav2Lip picks it up
    if hd_requested and sadtalker_engine is not None:
        try:
            return await sadtalker_engine.render(portrait_path, wav_path, output_path)
        except ZeroGpuQuotaExhaustedError:
            pass  # honest degrade, not a failure - Wav2Lip below picks it up
    return await wav2lip_engine.render(portrait_path, wav_path, output_path)
