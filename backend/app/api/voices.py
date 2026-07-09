"""specs/04-tasks/task-18-voice-cloning-voxcpm.md — personal voice
enrollment, preview, VoxCPM-designed personas, delete.

Enrollment is synchronous (no job queue) per the task's own "the whole flow
feels instant-ish (<30s)" - CPU-only validation + embedding extraction is
fast enough (benchmarked ~1-2s on this dev machine) that a background job
would only add latency, not save any.
"""
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.core.config import VOICE_TABLE, get_settings
from app.core.deps import get_current_user_id, get_db
from app.core.errors import AppError, NotFoundError
from app.core.ids import new_id
from app.engines.tts import openvoice
from app.engines.tts.openvoice import OpenVoiceConvertingEngine, OpenVoiceUnavailableError
from app.engines.tts.voxcpm_remote import VoxCPMEngineError, VoxCPMRemoteEngine
from app.models.voice_profile import VoiceDesignRequest, VoiceProfileOut
from app.moderation.consent import require_consent
from app.quota import gpu_budget
from app.services.voice_validation import estimate_prosody_gender, normalize_for_enrollment, validate_recording

router = APIRouter()

PASSAGES_DIR = Path(__file__).resolve().parents[2] / "assets" / "passages"

PREVIEW_TEXT = {
    "hi": "नमस्ते, यह आपकी अपनी आवाज़ का नमूना है।",
    "en": "Hello, this is a preview of your own voice.",
}


def _row_to_profile(row: sqlite3.Row) -> VoiceProfileOut:
    return VoiceProfileOut(
        id=row["id"],
        user_id=row["user_id"],
        kind=row["kind"],
        description=row["description"],
        base_voice=row["base_voice"],
        consented=bool(row["consented"]),
        created_at=row["created_at"],
    )


def _get_owned_profile(conn: sqlite3.Connection, profile_id: str, user_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM voice_profiles WHERE id = ? AND user_id = ?", (profile_id, user_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Voice profile {profile_id} not found")
    return row


def _profile_dir(settings, user_id: str, profile_id: str) -> Path:
    return settings.media_root / "users" / user_id / "voice_profiles" / profile_id


@router.get("/passage/{language}")
def get_passage(language: str) -> dict:
    path = PASSAGES_DIR / f"{language}.txt"
    if not path.exists():
        raise NotFoundError(f"No reading passage for language '{language}'")
    return {"language": language, "text": path.read_text(encoding="utf-8").strip()}


@router.get("", response_model=list[VoiceProfileOut])
def list_voice_profiles(
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[VoiceProfileOut]:
    rows = conn.execute(
        "SELECT * FROM voice_profiles WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    return [_row_to_profile(r) for r in rows]


@router.post("/enroll", response_model=VoiceProfileOut, status_code=201)
async def enroll_voice(
    sample: UploadFile = File(...),
    language: str = Form(...),
    consent: bool = Form(...),
    base_voice: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> VoiceProfileOut:
    # Likeness-artifact consent gate (hard invariant), shared with
    # app/api/avatars.py's own selfie consent gate.
    consented_at = require_consent(consent)
    if language not in VOICE_TABLE:
        raise AppError(f"Unsupported language '{language}'")

    settings = get_settings()
    raw_bytes = await sample.read()
    if not raw_bytes:
        raise AppError("Recording is empty", hint="Please record or upload a real sample")

    with tempfile.TemporaryDirectory() as tmp:
        raw_path = Path(tmp) / f"raw{Path(sample.filename or 'sample.wav').suffix or '.wav'}"
        raw_path.write_bytes(raw_bytes)

        try:
            validation = validate_recording(raw_path)
        except Exception as exc:  # noqa: BLE001 - an unreadable/corrupt upload, not a validation failure
            raise AppError("Could not read this recording", hint=str(exc)) from exc

        if not validation.ok:
            raise AppError("Recording didn't pass validation", hint="; ".join(validation.errors))

        # Re-recording replaces the single existing 'cloned' profile rather
        # than accumulating many - matches the spec's own "re-record any
        # time" framing (one personal voice per user, not a gallery of them).
        existing = conn.execute(
            "SELECT * FROM voice_profiles WHERE user_id = ? AND kind = 'cloned'", (user_id,)
        ).fetchone()
        if existing is not None:
            shutil.rmtree(_profile_dir(settings, user_id, existing["id"]), ignore_errors=True)
            conn.execute("DELETE FROM voice_profiles WHERE id = ?", (existing["id"],))
            conn.commit()

        profile_id = new_id()
        profile_dir = _profile_dir(settings, user_id, profile_id)
        sample_path = profile_dir / "sample.wav"
        normalize_for_enrollment(raw_path, sample_path)

        picked_gender = estimate_prosody_gender(sample_path)
        resolved_base_voice = base_voice or VOICE_TABLE[language][picked_gender]

        try:
            embedding = openvoice.extract_embedding(sample_path)
        except OpenVoiceUnavailableError as exc:
            raise AppError(
                "Voice enrollment isn't available right now", hint=str(exc)
            ) from exc

        embedding_path = profile_dir / "embedding.pt"
        openvoice.save_embedding(embedding, embedding_path)

    conn.execute(
        "INSERT INTO voice_profiles "
        "(id, user_id, kind, sample_path, embedding_path, base_voice, consented, consented_at) "
        "VALUES (?, ?, 'cloned', ?, ?, ?, 1, ?)",
        (profile_id, user_id, str(sample_path), str(embedding_path), resolved_base_voice, consented_at),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM voice_profiles WHERE id = ?", (profile_id,)).fetchone()
    return _row_to_profile(row)


@router.get("/{profile_id}/preview")
async def preview_voice(
    profile_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    profile = _get_owned_profile(conn, profile_id, user_id)
    settings = get_settings()
    cache_path = _profile_dir(settings, user_id, profile_id) / "preview.mp3"

    if not cache_path.exists():
        base_voice = profile["base_voice"] or VOICE_TABLE["en"]["female"]
        language = base_voice.split("-")[0]
        text = PREVIEW_TEXT.get(language, PREVIEW_TEXT["en"])
        engine = OpenVoiceConvertingEngine(Path(profile["embedding_path"]))
        try:
            await engine.speak(text, base_voice, cache_path)
        except OpenVoiceUnavailableError as exc:
            raise AppError("Couldn't render a preview right now", hint=str(exc)) from exc

    return FileResponse(cache_path, media_type="audio/mpeg")


@router.post("/design", response_model=VoiceProfileOut, status_code=201)
async def design_voice(
    payload: VoiceDesignRequest,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> VoiceProfileOut:
    """VoxCPM designed persona - "instead of the personal voice"
    (specs/01-requirements/11-personal-voice.md). Same honest-degradation
    shape as the SadTalker HD path: no ZeroGPU Space is deployed for this
    project yet, so this call fails with a clear, actionable message
    rather than a stack trace - not a fake success."""
    settings = get_settings()
    engine = VoxCPMRemoteEngine(
        space_id=settings.voxcpm_space_id,
        hf_token=settings.hf_token,
        conn=conn,
        daily_limit_seconds=settings.zerogpu_daily_seconds,
        persona_description=payload.description,
    )

    profile_id = new_id()
    profile_dir = _profile_dir(settings, user_id, profile_id)
    sample_path = profile_dir / "sample.mp3"
    try:
        await engine.speak(payload.description, "designed", sample_path)
    except VoxCPMEngineError as exc:
        raise AppError(
            "Designed voices aren't available yet",
            hint="The VoxCPM Space hasn't been deployed - use your enrolled voice or a stock voice for now",
        ) from exc

    conn.execute(
        "INSERT INTO voice_profiles (id, user_id, kind, description, sample_path, consented) "
        "VALUES (?, ?, 'designed', ?, ?, 1)",
        (profile_id, user_id, payload.description, str(sample_path)),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM voice_profiles WHERE id = ?", (profile_id,)).fetchone()
    return _row_to_profile(row)


@router.delete("/{profile_id}", status_code=204)
def delete_voice_profile(
    profile_id: str,
    user_id: str = Depends(get_current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    profile = _get_owned_profile(conn, profile_id, user_id)
    conn.execute("DELETE FROM voice_profiles WHERE id = ?", (profile_id,))
    conn.commit()

    # Working deletion of likeness artifacts (voice sample + embedding) -
    # hard invariant, same pattern as avatars.py's own selfie deletion.
    settings = get_settings()
    shutil.rmtree(_profile_dir(settings, user_id, profile["id"]), ignore_errors=True)
