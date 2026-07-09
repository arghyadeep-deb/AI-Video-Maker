"""Free-tier quotas reset at midnight Pacific — specs/02-research/01-free-llm-gemini-flash.md."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def pt_today() -> str:
    return datetime.now(PACIFIC).date().isoformat()


def iso_now() -> str:
    """Matches the shape of SQLite's `strftime('%Y-%m-%dT%H:%M:%fZ','now')`
    defaults elsewhere in the schema, so string comparison/sorting agrees.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
