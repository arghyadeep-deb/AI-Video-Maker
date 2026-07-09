"""Engine selection + ZeroGPU-fallback orchestration for Mode A rendering —
specs/03-design/04-mode-a-pipeline.md's engine-selection rules and
specs/04-tasks/task-11-talking-head.md's Implementation notes ("on ZeroGPU
quota error -> fall back to Wav2Lip and refund the slot"). The render_mode_a
pipeline itself (task-12) calls this rather than picking an engine directly.

Note: the three-tier "home GPU worker -> ZeroGPU -> CPU" routing described in
specs/03-design/11-gpu-worker.md is task-20a's job (the worker agent doesn't
exist yet). This task-11-scoped chooser only implements the two tiers that
actually exist right now: SadTalker ZeroGPU (HD, optional, budget-gated) and
Wav2Lip CPU (default, always available).
"""
from typing import Optional

from app.engines.talking_head.base import TalkingHeadEngine, TalkingHeadResult
from app.engines.talking_head.sadtalker_zerogpu import ZeroGpuQuotaExhaustedError


async def render_with_fallback(
    hd_requested: bool,
    sadtalker_engine: Optional[TalkingHeadEngine],
    wav2lip_engine: TalkingHeadEngine,
    portrait_path: str,
    wav_path: str,
    output_path: str,
) -> TalkingHeadResult:
    if hd_requested and sadtalker_engine is not None:
        try:
            return await sadtalker_engine.render(portrait_path, wav_path, output_path)
        except ZeroGpuQuotaExhaustedError:
            pass  # honest degrade, not a failure - Wav2Lip below picks it up
    return await wav2lip_engine.render(portrait_path, wav_path, output_path)
