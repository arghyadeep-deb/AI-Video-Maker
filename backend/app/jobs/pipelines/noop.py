"""Demo pipeline — 3 fake stages with sleeps, for worker tests and UI dev
(task-07's own Implementation notes ask for this explicitly).
"""
import asyncio

from app.jobs.registry import JobCancelled, JobContext, register_pipeline

STAGE_SLEEP_S = 0.05
STEPS_PER_STAGE = 4


async def _fake_stage(ctx: JobContext) -> None:
    for i in range(1, STEPS_PER_STAGE + 1):
        if ctx.cancelled():
            raise JobCancelled()
        await asyncio.sleep(STAGE_SLEEP_S)
        ctx.report(round(i / STEPS_PER_STAGE * 100))


NOOP_PIPELINE = [
    ("warm_up", _fake_stage),
    ("cook", _fake_stage),
    ("cool_down", _fake_stage),
]

register_pipeline("noop_render", NOOP_PIPELINE)
