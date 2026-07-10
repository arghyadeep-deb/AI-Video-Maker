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


def test_worker_online_false_when_no_agent_has_ever_polled(conn):
    settings = _settings(sadtalker_space_id="owner/sadtalker-space")
    state = compute_tier_state(conn, settings)
    assert state.worker_online is False
    assert state.worker_capabilities == []


def test_recent_worker_poll_flips_to_worker_tier(conn):
    """task-20a: a live agent poll makes the home worker tier 1, above
    ZeroGPU, and the badge promises footage only if scene_gen loaded."""
    from app.jobs import gpu_router

    settings = _settings(sadtalker_space_id="owner/sadtalker-space")
    gpu_router.record_worker_poll(conn, ["sadtalker", "scene_gen"], 15000)
    state = compute_tier_state(conn, settings)
    assert state.worker_online is True
    assert state.active_tier == "worker"
    assert state.label == "Generated footage available"
    assert state.worker_capabilities == ["sadtalker", "scene_gen"]


def test_worker_without_scene_gen_gets_honest_hd_label(conn):
    from app.jobs import gpu_router

    gpu_router.record_worker_poll(conn, ["sadtalker"], 15000)
    state = compute_tier_state(conn, _settings())
    assert state.active_tier == "worker"
    assert state.label == "HD available (home GPU)"


def test_stale_worker_poll_degrades_back_down_the_tiers(conn):
    from app.jobs import gpu_router

    settings = _settings(
        sadtalker_space_id="owner/sadtalker-space", worker_online_window_s=0.0
    )
    gpu_router.record_worker_poll(conn, ["sadtalker", "scene_gen"], 15000)
    state = compute_tier_state(conn, settings)
    assert state.worker_online is False
    assert state.active_tier == "zerogpu"
