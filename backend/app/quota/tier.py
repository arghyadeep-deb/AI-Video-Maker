"""GPU tier state — specs/04-tasks/task-15-quotas-fairness.md,
specs/03-design/11-gpu-worker.md's "three-tier GPU routing".

The home GPU worker itself (task-20a) doesn't exist yet - `worker_online`
is always False today, computed as a real field (not hardcoded into the
response shape) so the frontend badge and this function need no changes
once task-20a adds a real signal.
"""
import sqlite3
from typing import Literal, Optional

from pydantic import BaseModel

from app.core.config import Settings
from app.quota import gpu_budget

Tier = Literal["worker", "zerogpu", "cpu"]


class TierState(BaseModel):
    worker_online: bool
    zerogpu_seconds_remaining: float
    sadtalker_configured: bool
    active_tier: Tier
    label: str


def compute_tier_state(conn: sqlite3.Connection, settings: Settings) -> TierState:
    worker_online = False  # task-20a hasn't shipped a worker agent yet
    used = gpu_budget.seconds_used_today(conn)
    remaining = max(0.0, settings.zerogpu_daily_seconds - used)
    sadtalker_configured = bool(settings.sadtalker_space_id)

    if worker_online:
        active_tier: Tier = "worker"
        label = "Generated footage available"
    elif sadtalker_configured and remaining > 0:
        active_tier = "zerogpu"
        label = "HD avatar available (limited today)"
    else:
        active_tier = "cpu"
        label = "Photo mode only" if not sadtalker_configured else "HD limited today"

    return TierState(
        worker_online=worker_online,
        zerogpu_seconds_remaining=remaining,
        sadtalker_configured=sadtalker_configured,
        active_tier=active_tier,
        label=label,
    )
