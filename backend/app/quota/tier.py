"""GPU tier state — specs/04-tasks/task-15-quotas-fairness.md,
specs/03-design/11-gpu-worker.md's "three-tier GPU routing".

Task-20a made `worker_online` real: the home worker agent's polls stamp
`worker_status`, and this reads that presence plus the advertised
capability list (the agent only advertises engines that actually loaded,
so "Generated footage available" is honest by construction).
"""
import sqlite3
from typing import Literal

from pydantic import BaseModel

from app.core.config import Settings
from app.jobs import gpu_router
from app.quota import gpu_budget

Tier = Literal["worker", "zerogpu", "cpu"]


class TierState(BaseModel):
    worker_online: bool
    worker_capabilities: list[str]
    zerogpu_seconds_remaining: float
    sadtalker_configured: bool
    active_tier: Tier
    label: str


def compute_tier_state(conn: sqlite3.Connection, settings: Settings) -> TierState:
    worker_online = gpu_router.worker_online(conn, settings)
    capabilities = sorted(gpu_router.worker_capabilities(conn, settings))
    used = gpu_budget.seconds_used_today(conn)
    remaining = max(0.0, settings.zerogpu_daily_seconds - used)
    sadtalker_configured = bool(settings.sadtalker_space_id)

    if worker_online:
        active_tier: Tier = "worker"
        # The badge promises only what the agent's probe actually loaded.
        if "scene_gen" in capabilities:
            label = "Generated footage available"
        else:
            label = "HD available (home GPU)"
    elif sadtalker_configured and remaining > 0:
        active_tier = "zerogpu"
        label = "HD avatar available (limited today)"
    else:
        active_tier = "cpu"
        label = "Photo mode only" if not sadtalker_configured else "HD limited today"

    return TierState(
        worker_online=worker_online,
        worker_capabilities=capabilities,
        zerogpu_seconds_remaining=remaining,
        sadtalker_configured=sadtalker_configured,
        active_tier=active_tier,
        label=label,
    )
