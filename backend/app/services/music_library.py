"""Background-music track selection — specs/04-tasks/task-16-music-subtitle-styles.md.

Reads backend/assets/music/manifest.json (filename, mood, duration_s per
track) - see that directory's own LICENSES.md for per-track source/license.
"""
import json
import random
from pathlib import Path
from typing import Optional

MUSIC_DIR = Path(__file__).resolve().parents[2] / "assets" / "music"
MANIFEST_PATH = MUSIC_DIR / "manifest.json"


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def available_moods() -> list[str]:
    return sorted({t["mood"] for t in load_manifest()})


def pick_track(mood: str, rng: Optional[random.Random] = None) -> Optional[dict]:
    """A random track matching `mood` (its manifest entry, with an
    absolute `path` added), or None if no track is available for that
    mood - callers must degrade to no-music honestly rather than crash,
    same as every other free-tier fallback in this codebase."""
    tracks = [t for t in load_manifest() if t.get("mood") == mood]
    tracks = [t for t in tracks if (MUSIC_DIR / t["filename"]).exists()]
    if not tracks:
        return None
    chooser = rng or random
    chosen = dict(chooser.choice(tracks))
    chosen["path"] = str(MUSIC_DIR / chosen["filename"])
    return chosen
