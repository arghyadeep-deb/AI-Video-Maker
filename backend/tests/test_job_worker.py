import asyncio

import pytest

from app.db.connection import get_connection, run_migrations
from app.jobs import registry
from app.jobs.pipelines import noop  # noqa: F401 - registers noop_render
from app.jobs.queue import enqueue
from app.jobs.registry import JobCancelled, JobContext, register_pipeline
from app.jobs.worker import Worker


def _seed_user(conn, user_id: str = "u1"):
    conn.execute(
        "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (?, ?, 'x')",
        (user_id, f"{user_id}@test"),
    )
    conn.commit()


async def _wait_until(predicate, timeout_s: float = 5.0, interval_s: float = 0.02):
    elapsed = 0.0
    while elapsed < timeout_s:
        if predicate():
            return
        await asyncio.sleep(interval_s)
        elapsed += interval_s
    raise AssertionError("condition not met within timeout")


async def test_noop_job_runs_through_all_stages(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    conn = get_connection(db_path)
    _seed_user(conn)
    job_id = enqueue(conn, "u1", None, "noop_render", {})

    worker = Worker(db_path, poll_interval=0.01)
    await worker.start()
    try:
        await _wait_until(
            lambda: conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()["status"]
            in ("done", "failed", "cancelled")
        )
    finally:
        await worker.stop()

    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert row["status"] == "done"
    assert row["progress"] == 100
    assert row["started_at"] is not None
    assert row["finished_at"] is not None
    conn.close()


async def test_jobs_run_one_at_a_time_in_fifo_order(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    conn = get_connection(db_path)
    _seed_user(conn)
    first = enqueue(conn, "u1", None, "noop_render", {})
    second = enqueue(conn, "u1", None, "noop_render", {})

    worker = Worker(db_path, poll_interval=0.01)
    await worker.start()
    try:
        await _wait_until(
            lambda: conn.execute("SELECT status FROM jobs WHERE id=?", (second,)).fetchone()["status"] == "done"
        )
    finally:
        await worker.stop()

    first_row = conn.execute("SELECT * FROM jobs WHERE id=?", (first,)).fetchone()
    second_row = conn.execute("SELECT * FROM jobs WHERE id=?", (second,)).fetchone()
    assert first_row["finished_at"] <= second_row["started_at"], "second must not start before first finishes"
    conn.close()


async def test_cancel_stops_job_promptly(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    conn = get_connection(db_path)
    _seed_user(conn)
    job_id = enqueue(conn, "u1", None, "noop_render", {})

    worker = Worker(db_path, poll_interval=0.01)
    await worker.start()
    try:
        await _wait_until(
            lambda: conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()["status"] == "running"
        )
        worker.request_cancel(job_id)
        await _wait_until(
            lambda: conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()["status"]
            in ("cancelled", "done", "failed"),
            timeout_s=2.0,
        )
    finally:
        await worker.stop()

    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert row["status"] == "cancelled"
    conn.close()


async def test_exception_in_pipeline_marks_job_failed_with_message(tmp_path):
    async def _boom(ctx: JobContext) -> None:
        raise ValueError("synthetic failure for test")

    register_pipeline("voice_clone_prep", [("explode", _boom)])

    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    conn = get_connection(db_path)
    _seed_user(conn)
    job_id = enqueue(conn, "u1", None, "voice_clone_prep", {})

    worker = Worker(db_path, poll_interval=0.01)
    await worker.start()
    try:
        await _wait_until(
            lambda: conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()["status"] == "failed"
        )
    finally:
        await worker.stop()

    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert "synthetic failure for test" in row["error"]
    conn.close()


async def test_unregistered_job_type_fails_honestly(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    conn = get_connection(db_path)
    _seed_user(conn)
    # rerender_other_mode is a valid JOB_TYPE that's deliberately never
    # registered (task-17-post-render-tools.md: mode re-render clones a
    # project and reuses the existing render_mode_a/render_mode_b
    # pipelines directly, so this type never needs its own pipeline) -
    # rerender_scene used to be this test's example but gained a real
    # pipeline in task-17, and voice_clone_prep gets registered by an
    # earlier test in this same file (module-level registry state).
    job_id = enqueue(conn, "u1", None, "rerender_other_mode", {})

    worker = Worker(db_path, poll_interval=0.01)
    await worker.start()
    try:
        await _wait_until(
            lambda: conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()["status"] == "failed"
        )
    finally:
        await worker.stop()

    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert "No pipeline registered" in row["error"]
    conn.close()


def test_job_context_is_a_plain_dataclass():
    ctx = JobContext(
        job_id="j1", payload={}, report=lambda pct: None, cancelled=lambda: False, register_process=lambda p: None
    )
    assert ctx.job_id == "j1"


def test_stage_names_reflects_registered_pipeline():
    assert registry.stage_names("noop_render") == ["warm_up", "cook", "cool_down"]


def test_job_cancelled_is_an_exception():
    with pytest.raises(JobCancelled):
        raise JobCancelled()
