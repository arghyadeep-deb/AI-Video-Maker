"""Unit tests for the gpu_tasks queue + three-tier routing primitives —
task-20a's Tests section: "router tier selection matrix; lease expiry;
capability negotiation"."""
import asyncio

import pytest

from app.core.config import Settings
from app.db.connection import get_connection, run_migrations
from app.jobs import gpu_router
from app.jobs.gpu_router import GpuTaskFailed


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    conn = get_connection(db_path)
    yield conn, db_path
    conn.close()


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


# --- worker presence ---------------------------------------------------------

def test_worker_offline_with_no_poll_ever(db):
    conn, _ = db
    assert gpu_router.worker_online(conn, _settings()) is False
    assert gpu_router.worker_capabilities(conn, _settings()) == set()


def test_worker_online_after_recent_poll(db):
    conn, _ = db
    gpu_router.record_worker_poll(conn, ["sadtalker", "scene_gen"], 15000)
    settings = _settings()
    assert gpu_router.worker_online(conn, settings) is True
    assert gpu_router.worker_capabilities(conn, settings) == {"sadtalker", "scene_gen"}


def test_worker_goes_offline_when_poll_is_stale(db):
    conn, _ = db
    gpu_router.record_worker_poll(conn, ["sadtalker"], 15000)
    # A zero-width freshness window makes any stamp instantly stale.
    settings = _settings(worker_online_window_s=0.0)
    assert gpu_router.worker_online(conn, settings) is False
    assert gpu_router.worker_capabilities(conn, settings) == set()


def test_capabilities_update_on_each_poll(db):
    conn, _ = db
    gpu_router.record_worker_poll(conn, ["sadtalker", "scene_gen"], 15000)
    gpu_router.record_worker_poll(conn, ["sadtalker"], 6000)  # owner's app ate VRAM
    assert gpu_router.worker_capabilities(conn, _settings()) == {"sadtalker"}


# --- capability negotiation --------------------------------------------------

def test_lease_respects_capabilities(db):
    conn, _ = db
    settings = _settings()
    gpu_router.submit_task(conn, "scene_gen", {}, [])
    assert gpu_router.lease_next_task(conn, ["sadtalker"], settings) is None
    leased = gpu_router.lease_next_task(conn, ["sadtalker", "scene_gen"], settings)
    assert leased is not None and leased["kind"] == "scene_gen"


def test_lease_is_fifo_within_capabilities(db):
    conn, _ = db
    settings = _settings()
    first = gpu_router.submit_task(conn, "sadtalker", {}, [])
    second = gpu_router.submit_task(conn, "sadtalker", {}, [])
    assert gpu_router.lease_next_task(conn, ["sadtalker"], settings)["id"] == first
    assert gpu_router.lease_next_task(conn, ["sadtalker"], settings)["id"] == second


def test_empty_capabilities_lease_nothing(db):
    conn, _ = db
    gpu_router.submit_task(conn, "sadtalker", {}, [])
    assert gpu_router.lease_next_task(conn, [], _settings()) is None


# --- lease expiry ------------------------------------------------------------

def test_expired_lease_requeues_then_fails_after_max_attempts(db):
    conn, _ = db
    # Timeout 0 = every heartbeat is instantly stale; max 2 lease grants.
    settings = _settings(worker_lease_timeout_s=0.0, worker_task_max_attempts=2)
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])

    assert gpu_router.lease_next_task(conn, ["sadtalker"], settings)["id"] == task_id
    gpu_router.sweep_expired_leases(conn, settings)
    row = conn.execute("SELECT * FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    assert row["status"] == "queued"  # attempt 1 of 2: back in the queue
    assert row["attempts"] == 1

    assert gpu_router.lease_next_task(conn, ["sadtalker"], settings)["id"] == task_id
    gpu_router.sweep_expired_leases(conn, settings)
    row = conn.execute("SELECT * FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    assert row["status"] == "failed"  # attempts exhausted
    assert "worker lost" in row["error"]


def test_healthy_lease_survives_sweep(db):
    conn, _ = db
    settings = _settings()  # default 35 s timeout, heartbeat is fresh
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    gpu_router.lease_next_task(conn, ["sadtalker"], settings)
    assert gpu_router.sweep_expired_leases(conn, settings) == 0
    row = conn.execute("SELECT * FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    assert row["status"] == "leased"


# --- heartbeat / complete / fail semantics -----------------------------------

def test_heartbeat_on_leased_task_true_and_updates_progress(db):
    conn, _ = db
    settings = _settings()
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    gpu_router.lease_next_task(conn, ["sadtalker"], settings)
    assert gpu_router.heartbeat(conn, task_id, 42.0) is True
    row = conn.execute("SELECT progress FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    assert row["progress"] == 42.0


def test_heartbeat_after_requeue_tells_agent_to_abort(db):
    conn, _ = db
    settings = _settings(worker_lease_timeout_s=0.0)
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    gpu_router.lease_next_task(conn, ["sadtalker"], settings)
    gpu_router.sweep_expired_leases(conn, settings)  # requeued
    assert gpu_router.heartbeat(conn, task_id, 50.0) is False


def test_complete_only_works_while_leased(db, tmp_path):
    conn, _ = db
    settings = _settings()
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    result = tmp_path / "out.mp4"
    assert gpu_router.complete_task(conn, task_id, result) is False  # still queued
    gpu_router.lease_next_task(conn, ["sadtalker"], settings)
    assert gpu_router.complete_task(conn, task_id, result) is True
    row = conn.execute("SELECT * FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    assert row["status"] == "done" and row["result_path"] == str(result)


def test_agent_reported_failure_is_permanent(db):
    conn, _ = db
    settings = _settings()
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    gpu_router.lease_next_task(conn, ["sadtalker"], settings)
    assert gpu_router.fail_task(conn, task_id, "CUDA OOM") is True
    row = conn.execute("SELECT * FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    assert row["status"] == "failed" and "CUDA OOM" in row["error"]


# --- wait_for_task -----------------------------------------------------------

def test_wait_returns_done_row(db, tmp_path):
    conn, db_path = db
    settings = _settings()
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    gpu_router.lease_next_task(conn, ["sadtalker"], settings)
    gpu_router.complete_task(conn, task_id, tmp_path / "out.mp4")
    row = asyncio.run(gpu_router.wait_for_task(db_path, task_id, settings, poll_interval_s=0.01))
    assert row["status"] == "done"


def test_wait_raises_on_failure(db):
    conn, db_path = db
    settings = _settings()
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    gpu_router.lease_next_task(conn, ["sadtalker"], settings)
    gpu_router.fail_task(conn, task_id, "engine crashed")
    with pytest.raises(GpuTaskFailed, match="engine crashed"):
        asyncio.run(gpu_router.wait_for_task(db_path, task_id, settings, poll_interval_s=0.01))


def test_wait_sweeps_leases_itself_when_agent_vanishes(db):
    """The waiter must not hang until its own timeout when the agent dies:
    its loop runs the expiry sweep (nobody else would - a dead agent stops
    polling), so exhausted attempts surface as GpuTaskFailed promptly."""
    conn, db_path = db
    settings = _settings(worker_lease_timeout_s=0.0, worker_task_max_attempts=1)
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    gpu_router.lease_next_task(conn, ["sadtalker"], settings)  # attempt 1, then silence
    with pytest.raises(GpuTaskFailed, match="worker lost"):
        asyncio.run(gpu_router.wait_for_task(db_path, task_id, settings, poll_interval_s=0.01))


def test_wait_times_out_and_cancels_task(db):
    conn, db_path = db
    settings = _settings(worker_task_wait_timeout_s=0.05)
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])  # never leased
    with pytest.raises(GpuTaskFailed, match="timed out"):
        asyncio.run(gpu_router.wait_for_task(db_path, task_id, settings, poll_interval_s=0.01))
    row = conn.execute("SELECT status FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    assert row["status"] == "cancelled"


def test_wait_honors_pipeline_cancel(db):
    conn, db_path = db
    settings = _settings()
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    with pytest.raises(GpuTaskFailed, match="cancelled"):
        asyncio.run(
            gpu_router.wait_for_task(
                db_path, task_id, settings, cancelled=lambda: True, poll_interval_s=0.01
            )
        )
    row = conn.execute("SELECT status FROM gpu_tasks WHERE id = ?", (task_id,)).fetchone()
    assert row["status"] == "cancelled"


# --- signed one-time URLs ----------------------------------------------------

def test_signed_url_single_use(db, tmp_path):
    conn, _ = db
    settings = _settings()
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    token = gpu_router.mint_signed_url(conn, task_id, str(tmp_path / "in.jpg"), settings)
    assert gpu_router.consume_signed_url(conn, token) == str(tmp_path / "in.jpg")
    assert gpu_router.consume_signed_url(conn, token) is None  # second use rejected


def test_signed_url_expiry(db, tmp_path):
    conn, _ = db
    settings = _settings(worker_signed_url_ttl_s=-1.0)  # born expired
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    token = gpu_router.mint_signed_url(conn, task_id, str(tmp_path / "in.jpg"), settings)
    assert gpu_router.consume_signed_url(conn, token) is None


def test_signed_url_unknown_token(db):
    conn, _ = db
    assert gpu_router.consume_signed_url(conn, "no-such-token") is None


def test_signed_tokens_are_not_uuidv7_shaped(db, tmp_path):
    """The token is the credential - it must be full-entropy secrets
    randomness, not a time-prefixed (partially predictable) UUIDv7."""
    conn, _ = db
    settings = _settings()
    task_id = gpu_router.submit_task(conn, "sadtalker", {}, [])
    token = gpu_router.mint_signed_url(conn, task_id, "x", settings)
    assert "-" not in token or len(token) > 40  # token_urlsafe(32), not a UUID string
    assert len(token) >= 40
