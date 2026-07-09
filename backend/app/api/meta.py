"""`/api/meta/*` — environment doctor + static reference data."""
import random
import subprocess

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.connection import get_connection
from app.engines.tts.base import TTSEngine
from app.engines.tts.edge import EdgeTTSEngine
from app.quota.tier import TierState, compute_tier_state
from app.services import music_library
from app.services.ffmpeg import probe
from app.services.ffmpeg.probe import ffmpeg_path

router = APIRouter()

# 3-s-ish sample line per language prefix (hi-IN-*, en-IN-*/en-US-* share "en").
PREVIEW_TEXT = {
    "hi": "नमस्ते, यह आपकी आवाज़ का नमूना है।",
    "en": "Hello, this is a preview of this voice.",
}


def get_tts_engine() -> TTSEngine:
    return EdgeTTSEngine()


def _cuda_available() -> bool:
    try:
        import torch  # noqa: PLC0415 (optional, heavy — worker-only dependency)

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


@router.get("/health")
def health():
    settings = get_settings()
    ffmpeg = probe.ffmpeg_status()

    conn = get_connection(settings.db_path)
    try:
        schema_version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    return {
        "ffmpeg": ffmpeg,
        "subtitle_filters_available": probe.subtitle_filters_available(),
        "cuda_available": _cuda_available(),
        "keys_configured": {
            "gemini": bool(settings.gemini_api_key),
            "pexels": bool(settings.pexels_api_key),
            "pixabay": bool(settings.pixabay_api_key),
        },
        "db_migrated": schema_version > 0,
        "schema_version": schema_version,
    }


@router.get("/tier", response_model=TierState)
def tier():
    """GPU tier state for the UI badge (task-15) - "Generated footage
    available" / "HD available (limited today)" / "Photo mode only". Public
    like /health: no user data, just site-wide capacity state, and the
    generate page needs it before establishing anything project-specific.
    """
    settings = get_settings()
    conn = get_connection(settings.db_path)
    try:
        return compute_tier_state(conn, settings)
    finally:
        conn.close()


@router.get("/voices")
def voices():
    return get_settings().voice_table


def _all_voice_ids(voice_table: dict) -> set[str]:
    return {voice_id for pair in voice_table.values() for voice_id in pair.values()}


@router.get("/voices/{voice_id}/preview")
async def voice_preview(voice_id: str, engine: TTSEngine = Depends(get_tts_engine)):
    settings = get_settings()
    if voice_id not in _all_voice_ids(settings.voice_table):
        raise NotFoundError(f"Unknown voice {voice_id}")

    cache_path = settings.media_root / "voice_previews" / f"{voice_id}.mp3"
    if not cache_path.exists():
        language_prefix = voice_id.split("-")[0]
        text = PREVIEW_TEXT.get(language_prefix, PREVIEW_TEXT["en"])
        await engine.speak(text, voice_id, cache_path)

    return FileResponse(cache_path, media_type="audio/mpeg")


@router.get("/music/moods")
def music_moods() -> list[str]:
    return music_library.available_moods()


@router.get("/music/preview/{mood}")
def music_preview(mood: str):
    """5s clip of one representative track per mood - specs/04-tasks/task-16-music-subtitle-styles.md's
    "music toggle + mood picker with 5 s preview". Deterministic (not the
    same random draw a render would use) so the same preview plays every
    time a user samples a mood."""
    settings = get_settings()
    track = music_library.pick_track(mood, rng=random.Random(0))
    if track is None:
        raise NotFoundError(f"No tracks available for mood '{mood}'")

    cache_path = settings.media_root / "music_previews" / f"{mood}.mp3"
    if not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = ffmpeg_path() or "ffmpeg"
        subprocess.run(
            [ffmpeg_bin, "-y", "-i", track["path"], "-t", "5", "-c", "copy", str(cache_path)],
            check=True, capture_output=True, timeout=15,
        )

    return FileResponse(cache_path, media_type="audio/mpeg")
