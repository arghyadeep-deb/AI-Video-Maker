import pytest

from app.core.config import Settings
from app.db.connection import get_connection, run_migrations
from app.quota import gpu_budget
from app.quota.tier import compute_tier_state


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_worker_offline_no_space_deployed_is_cpu_only(conn):
    settings = _settings(sadtalker_space_id=None)
    state = compute_tier_state(conn, settings)
    assert state.worker_online is False
    assert state.sadtalker_configured is False
    assert state.active_tier == "cpu"
    assert state.label == "Photo mode only"


def test_space_deployed_with_budget_remaining_is_zerogpu_tier(conn):
    settings = _settings(sadtalker_space_id="owner/sadtalker-space", zerogpu_daily_seconds=300)
    state = compute_tier_state(conn, settings)
    assert state.active_tier == "zerogpu"
    assert state.zerogpu_seconds_remaining == 300


def test_space_deployed_but_budget_exhausted_degrades_to_cpu(conn):
    settings = _settings(sadtalker_space_id="owner/sadtalker-space", zerogpu_daily_seconds=100)
    gpu_budget.record_usage(conn, 100)
    state = compute_tier_state(conn, settings)
    assert state.active_tier == "cpu"
    assert state.label == "HD limited today"
    assert state.zerogpu_seconds_remaining == 0


def test_zerogpu_seconds_remaining_reflects_partial_usage(conn):
    settings = _settings(sadtalker_space_id="owner/sadtalker-space", zerogpu_daily_seconds=300)
    gpu_budget.record_usage(conn, 120)
    state = compute_tier_state(conn, settings)
    assert state.zerogpu_seconds_remaining == 180


def test_worker_online_is_always_false_until_task_20a(conn):
    """task-20a hasn't shipped a worker agent - this is a locked, honest
    fact about the current build, not a config toggle."""
    settings = _settings(sadtalker_space_id="owner/sadtalker-space")
    state = compute_tier_state(conn, settings)
    assert state.worker_online is False
