"""SQLite connection + migrations.

Plain numbered `.sql` files applied at startup, tracked via `PRAGMA
user_version` — no Alembic ceremony, per specs/01-requirements/07-free-stack-lock.md.
"""
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI resolves each sync dependency via
    # run_in_threadpool, and successive dependencies on the same request can
    # land on different worker threads. Access here is still strictly
    # sequential per request (dependencies resolve one after another, then
    # the handler runs, then the connection is closed) — never concurrent —
    # so relaxing sqlite3's same-thread check is safe.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)


def run_migrations(db_path: Path) -> int:
    """Apply any migration numbered above the DB's current user_version.

    Returns the resulting schema version. Idempotent: re-running against an
    already-migrated DB applies nothing.
    """
    conn = get_connection(db_path)
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        version = current
        for path in _migration_files():
            number = int(path.name.split("_", 1)[0])
            if number <= current:
                continue
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {number}")
            version = number
        conn.commit()
        return version
    finally:
        conn.close()
