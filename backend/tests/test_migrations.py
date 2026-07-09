import threading

from app.db.connection import MIGRATIONS_DIR, get_connection, run_migrations

EXPECTED_TABLES = {
    "users",
    "credits",
    "usage",
    "voice_profiles",
    "avatars",
    "projects",
    "script_versions",
    "jobs",
    "media_assets",
}

# Derived, not hardcoded, so adding a migration file doesn't require editing
# this test - it just needs to keep applying cleanly.
LATEST_MIGRATION = max(int(p.name.split("_", 1)[0]) for p in MIGRATIONS_DIR.glob("*.sql"))


def _table_names(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_migration_creates_full_schema(tmp_path):
    db_path = tmp_path / "app.db"
    version = run_migrations(db_path)

    assert version == LATEST_MIGRATION
    conn = get_connection(db_path)
    try:
        assert EXPECTED_TABLES.issubset(_table_names(conn))
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_MIGRATION
    finally:
        conn.close()


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)

    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')"
    )
    conn.commit()
    conn.close()

    # Re-running must not error and must not wipe existing data.
    version = run_migrations(db_path)
    assert version == LATEST_MIGRATION

    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE id = 'u1'").fetchone()
        assert row is not None
    finally:
        conn.close()


def test_fresh_db_has_no_tables_before_migration(tmp_path):
    db_path = tmp_path / "app.db"
    conn = get_connection(db_path)
    try:
        assert _table_names(conn) == set()
    finally:
        conn.close()


def test_connection_usable_from_a_different_thread(tmp_path):
    """Regression test: FastAPI resolves each sync dependency via
    run_in_threadpool, and successive dependencies on one request can land
    on different worker threads. A connection opened without
    check_same_thread=False raises sqlite3.ProgrammingError the first time
    a later dependency (e.g. get_current_user_id) touches it from a
    different thread than the one that opened it.
    """
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    conn = get_connection(db_path)
    errors: list[Exception] = []

    def use_from_other_thread():
        try:
            conn.execute("SELECT 1").fetchone()
        except Exception as exc:  # noqa: BLE001 - want to see any failure
            errors.append(exc)

    try:
        thread = threading.Thread(target=use_from_other_thread)
        thread.start()
        thread.join()
        assert errors == []
    finally:
        conn.close()
