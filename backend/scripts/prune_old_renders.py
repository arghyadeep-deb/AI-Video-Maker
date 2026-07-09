"""Deletes rendered MP4s older than the retention window — resolves open
decision #13 (specs/01-requirements/09-open-decisions.md): "Auto-prune MP4s
after 14 days (projects/scripts kept, re-render free-of-charge if pruned)".

Only the output.mp4 file and the project's `output_path` column are
cleared; the project row, its accepted script, and all media_assets stay
intact, so the library still shows the project (as "generating"/needing a
fresh render, per task-13's own read-time status derivation) and a
re-render costs nothing extra.

Usage (from backend/, typically via deploy/retention_cron.sh):
    python scripts/prune_old_renders.py [--days N] [--dry-run]
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.db.connection import get_connection, run_migrations  # noqa: E402

DEFAULT_RETENTION_DAYS = 14


def _cutoff_iso(days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def find_prunable(conn, cutoff_iso: str) -> list[dict]:
    """Projects whose most recent completed render job finished before the
    cutoff. Uses the render job's own `finished_at`, not `projects.created_at`
    (a project can be re-rendered long after it was first created)."""
    rows = conn.execute(
        """
        SELECT p.id AS project_id, p.output_path, MAX(j.finished_at) AS last_rendered_at
        FROM projects p
        JOIN jobs j ON j.project_id = p.id
        WHERE p.output_path IS NOT NULL
          AND j.type IN ('render_mode_a', 'render_mode_b', 'rerender_scene')
          AND j.status = 'done'
        GROUP BY p.id
        HAVING last_rendered_at < ?
        """,
        (cutoff_iso,),
    ).fetchall()
    return [dict(row) for row in rows]


def prune(conn, days: int, dry_run: bool) -> int:
    cutoff_iso = _cutoff_iso(days)
    candidates = find_prunable(conn, cutoff_iso)

    pruned = 0
    for row in candidates:
        output_path = Path(row["output_path"])
        print(
            f"[{'dry-run' if dry_run else 'prune'}] project {row['project_id']}: "
            f"last rendered {row['last_rendered_at']} (before {cutoff_iso}) -> {output_path}"
        )
        if dry_run:
            continue

        output_path.unlink(missing_ok=True)
        conn.execute("UPDATE projects SET output_path = NULL WHERE id = ?", (row["project_id"],))
        pruned += 1

    if not dry_run:
        conn.commit()
    return pruned


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    run_migrations(settings.db_path)
    conn = get_connection(settings.db_path)
    try:
        pruned = prune(conn, args.days, args.dry_run)
    finally:
        conn.close()

    print(f"{'Would prune' if args.dry_run else 'Pruned'} {pruned} project(s) older than {args.days} days.")


if __name__ == "__main__":
    main()
