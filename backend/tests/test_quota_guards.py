import pytest

from app.db.connection import get_connection, run_migrations
from app.engines.script_llm import QuotaExhaustedError
from app.quota import guards


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


def test_usage_today_starts_at_zero(conn):
    assert guards.usage_today(conn, "gemini_text") == 0


def test_increment_usage_accumulates(conn):
    guards.increment_usage(conn, "gemini_text")
    guards.increment_usage(conn, "gemini_text")
    assert guards.usage_today(conn, "gemini_text") == 2


def test_increment_usage_with_n(conn):
    guards.increment_usage(conn, "genai_image", n=5)
    assert guards.usage_today(conn, "genai_image") == 5


def test_guard_allows_calls_under_cap(conn):
    guards.increment_usage(conn, "gemini_text", n=5)
    guards.guard(conn, "gemini_text", cap=10)  # must not raise


def test_guard_blocks_calls_at_cap(conn):
    guards.increment_usage(conn, "gemini_text", n=10)
    with pytest.raises(QuotaExhaustedError):
        guards.guard(conn, "gemini_text", cap=10)


def test_guard_blocks_calls_over_cap(conn):
    guards.increment_usage(conn, "gemini_text", n=15)
    with pytest.raises(QuotaExhaustedError):
        guards.guard(conn, "gemini_text", cap=10)


def test_counters_are_independent_per_provider(conn):
    guards.increment_usage(conn, "gemini_text", n=10)
    assert guards.usage_today(conn, "genai_image") == 0
