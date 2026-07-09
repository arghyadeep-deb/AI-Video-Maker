"""Pipeline registry — specs/03-design/07-job-queue-and-progress.md.

Each pipeline is an ordered list of `(stage_name, coroutine)` steps. The
worker calls each step with a `JobContext` giving it a `report(pct)`
callback, a `cancelled()` probe to check between/during long operations,
and `register_process()` so long-running subprocesses (FFmpeg, SadTalker,
...) can be killed promptly on cancel.
"""
import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

JOB_TYPES = (
    "noop_render",
    "avatar_styling",
    "render_mode_a",
    "render_mode_b",
    "rerender_scene",
    "rerender_other_mode",
    "voice_clone_prep",
)


class JobCancelled(Exception):
    """Raised by a pipeline step (or the worker itself) when a cancel was
    requested mid-stage."""


class AwaitingUser(Exception):
    """Raised by a pipeline step to park the job as `awaiting_user` instead
    of `done` - the job's own work finished, but something needs human
    review/action (e.g. avatar portrait approval, task-10) before anything
    downstream continues. Not a failure; no further stages run.
    """


@dataclass
class JobContext:
    job_id: str
    payload: dict
    report: Callable[[float], None]
    cancelled: Callable[[], bool]
    register_process: Callable[[asyncio.subprocess.Process], None]


Step = Callable[[JobContext], Awaitable[None]]
Pipeline = list[tuple[str, Step]]

_PIPELINES: dict[str, Pipeline] = {}


def register_pipeline(job_type: str, stages: Pipeline) -> None:
    if job_type not in JOB_TYPES:
        raise ValueError(f"Unknown job type {job_type!r} — add it to JOB_TYPES first")
    _PIPELINES[job_type] = stages


def get_pipeline(job_type: str) -> Pipeline:
    if job_type not in _PIPELINES:
        raise KeyError(f"No pipeline registered for job type {job_type!r}")
    return _PIPELINES[job_type]


def stage_names(job_type: str) -> list[str]:
    return [name for name, _ in get_pipeline(job_type)]


def is_registered(job_type: str) -> bool:
    return job_type in _PIPELINES
