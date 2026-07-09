import sqlite3

import pytest

from app.db.connection import get_connection, run_migrations
from app.quota import gpu_budget


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    connection = get_connection(db_path)
    connection.execute("INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')")
    connection.commit()
    yield connection
    connection.close()


def test_no_usage_means_full_budget_available(conn: sqlite3.Connection):
    assert gpu_budget.seconds_used_today(conn) == 0.0
    assert gpu_budget.has_budget(conn, daily_limit_seconds=300, estimate_seconds=60) is True


def test_record_usage_accumulates(conn: sqlite3.Connection):
    gpu_budget.record_usage(conn, 40)
    gpu_budget.record_usage(conn, 25)
    assert gpu_budget.seconds_used_today(conn) == 65.0


def test_has_budget_respects_the_daily_limit(conn: sqlite3.Connection):
    gpu_budget.record_usage(conn, 280)
    assert gpu_budget.has_budget(conn, daily_limit_seconds=300, estimate_seconds=15) is True
    assert gpu_budget.has_budget(conn, daily_limit_seconds=300, estimate_seconds=25) is False


def test_refund_reverses_a_charge(conn: sqlite3.Connection):
    gpu_budget.record_usage(conn, 50)
    gpu_budget.refund_usage(conn, 50)
    assert gpu_budget.seconds_used_today(conn) == 0.0


def test_refund_never_goes_negative(conn: sqlite3.Connection):
    gpu_budget.record_usage(conn, 10)
    gpu_budget.refund_usage(conn, 999)
    assert gpu_budget.seconds_used_today(conn) == 0.0
