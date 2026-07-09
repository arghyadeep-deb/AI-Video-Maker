import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from prune_old_renders import find_prunable, prune  # noqa: E402

from app.core.config import get_settings
from app.core.ids import new_id
from app.db.connection import get_connection, run_migrations


def _iso(days_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _seed_rendered_project(conn, tmp_path, finished_days_ago: float):
    project_id = new_id()
    output_path = tmp_path / f"{project_id}.mp4"
    output_path.write_bytes(b"fake-mp4")

    conn.execute("INSERT OR IGNORE INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')")
    conn.execute(
        "INSERT INTO projects (id, user_id, description, language, duration_s, format, status, output_path) "
        "VALUES (?, 'u1', 'd', 'hi', 30, '9x16', 'done', ?)",
        (project_id, str(output_path)),
    )
    conn.execute(
        "INSERT INTO jobs (id, user_id, project_id, type, status, payload_json, finished_at) "
        "VALUES (?, 'u1', ?, 'render_mode_b', 'done', '{}', ?)",
        (new_id(), project_id, _iso(finished_days_ago)),
    )
    conn.commit()
    return project_id, output_path


def _conn(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    get_settings.cache_clear()
    settings = get_settings()
    run_migrations(settings.db_path)
    return get_connection(settings.db_path)


def test_recently_rendered_project_is_not_pruned(monkeypatch, tmp_path):
    conn = _conn(monkeypatch, tmp_path)
    _seed_rendered_project(conn, tmp_path, finished_days_ago=1)

    cutoff = _iso(14)
    assert find_prunable(conn, cutoff) == []


def test_old_render_is_pruned_project_row_kept(monkeypatch, tmp_path):
    conn = _conn(monkeypatch, tmp_path)
    project_id, output_path = _seed_rendered_project(conn, tmp_path, finished_days_ago=20)

    pruned_count = prune(conn, days=14, dry_run=False)
    assert pruned_count == 1
    assert not output_path.exists()

    row = conn.execute("SELECT output_path FROM projects WHERE id = ?", (project_id,)).fetchone()
    assert row["output_path"] is None
    # The project row itself, and its jobs, are untouched.
    assert conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is not None


def test_dry_run_does_not_delete_anything(monkeypatch, tmp_path):
    conn = _conn(monkeypatch, tmp_path)
    project_id, output_path = _seed_rendered_project(conn, tmp_path, finished_days_ago=20)

    pruned_count = prune(conn, days=14, dry_run=True)
    assert pruned_count == 0
    assert output_path.exists()

    row = conn.execute("SELECT output_path FROM projects WHERE id = ?", (project_id,)).fetchone()
    assert row["output_path"] is not None


def test_a_project_re_rendered_after_its_first_stale_render_is_not_pruned(monkeypatch, tmp_path):
    """A project rendered 20 days ago but re-rendered (rerender_scene) 1 day
    ago must use the MOST RECENT render's timestamp, not the first one."""
    conn = _conn(monkeypatch, tmp_path)
    project_id, output_path = _seed_rendered_project(conn, tmp_path, finished_days_ago=20)

    conn.execute(
        "INSERT INTO jobs (id, user_id, project_id, type, status, payload_json, finished_at) "
        "VALUES (?, 'u1', ?, 'rerender_scene', 'done', '{}', ?)",
        (new_id(), project_id, _iso(1)),
    )
    conn.commit()

    assert find_prunable(conn, _iso(14)) == []
