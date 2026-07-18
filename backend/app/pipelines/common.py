"""Shared helpers between render_mode_a and render_mode_b —
specs/03-design/08-data-model.md's project directory layout and the
accepted-script-version lookup both pipelines need identically.
"""
import json
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.engines.tts.base import PersonalVoiceUnavailableError, SpeechResult, TTSEngine
from app.models.script import Scene


class PipelineError(Exception):
    pass


def project_dir(media_root: Path, user_id: str, project_id: str) -> Path:
    return media_root / "users" / user_id / "projects" / project_id


def load_project_and_scenes(conn, project_id: str) -> tuple:
    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    version_id = project["accepted_version_id"]
    if version_id is None:
        raise PipelineError(f"Project {project_id} has no accepted script version")
    version = conn.execute(
        "SELECT * FROM script_versions WHERE id = ?", (version_id,)
    ).fetchone()
    scenes = [Scene.model_validate(s) for s in json.loads(version["scenes_json"])]
    return project, scenes


class FallbackNarrationEngine(TTSEngine):
    """Every render defaults to the user's enrolled voice; stock voice
    only with a visible notice - hard invariant, specs/AGENT-PLAYBOOK.md.
    Tries the personal engine (or tier chain) first when the user has
    one; falls back to the stock engine on ANY personal-tier failure,
    recording which path was actually used (and why) so callers can
    surface an explicit notice rather than silently substituting a
    different voice. `used_stock_fallback`/`fallback_reason` reflect the
    LAST `speak()` call.
    """

    def __init__(self, primary: Optional[TTSEngine], stock: TTSEngine):
        self._primary = primary
        self._stock = stock
        self.used_stock_fallback = primary is None
        self.fallback_reason: Optional[str] = None if primary is not None else "not_enrolled"

    async def speak(self, text: str, voice: str, out_path: Path, rate: Optional[str] = None) -> SpeechResult:
        if self._primary is not None:
            try:
                result = await self._primary.speak(text, voice, out_path, rate)
                self.used_stock_fallback = False
                self.fallback_reason = None
                return result
            except PersonalVoiceUnavailableError as exc:
                self.used_stock_fallback = True
                self.fallback_reason = str(exc)
        return await self._stock.speak(text, voice, out_path, rate)


class PersonalVoiceChain(TTSEngine):
    """Task-23 voice upgrade: tries each personal-voice tier in order
    (Chatterbox expressive cloning -> OpenVoice tone conversion), all
    still the user's OWN enrolled voice - so falling between them needs no
    user-facing notice; only falling out of the chain entirely (to stock)
    does, which FallbackNarrationEngine above already handles. Raises the
    last tier's error so that logic keeps working unchanged."""

    def __init__(self, tiers: list[TTSEngine]):
        if not tiers:
            raise ValueError("PersonalVoiceChain needs at least one tier")
        self._tiers = tiers

    async def speak(self, text: str, voice: str, out_path: Path, rate: Optional[str] = None) -> SpeechResult:
        last_error: Optional[PersonalVoiceUnavailableError] = None
        for tier in self._tiers:
            try:
                return await tier.speak(text, voice, out_path, rate)
            except PersonalVoiceUnavailableError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error


def make_narration_engine(conn, user_id: str, stock_engine: TTSEngine) -> FallbackNarrationEngine:
    """Looks up the user's enrolled ('cloned') voice profile, if any, and
    builds the personal-voice tier chain (task-23 voice upgrade):
    Chatterbox Multilingual expressive cloning (public Space, needs the
    raw enrollment sample) -> OpenVoice tone conversion (local CPU) ->
    stock voice with explicit notice. Every tier before stock speaks in
    the user's own enrolled voice - the hard invariant holds throughout."""
    row = conn.execute(
        "SELECT * FROM voice_profiles WHERE user_id = ? AND kind = 'cloned'", (user_id,)
    ).fetchone()
    if row is None:
        return FallbackNarrationEngine(primary=None, stock=stock_engine)

    settings = get_settings()
    tiers: list[TTSEngine] = []

    sample_path = row["sample_path"] if "sample_path" in row.keys() else None
    if settings.chatterbox_narration_enabled and sample_path and Path(sample_path).exists():
        from app.engines.tts.chatterbox_remote import ChatterboxRemoteEngine

        tiers.append(
            ChatterboxRemoteEngine(
                reference_wav_path=Path(sample_path), hf_token=settings.hf_token
            )
        )

    from app.engines.tts.openvoice import OpenVoiceConvertingEngine, is_available

    if is_available():
        tiers.append(OpenVoiceConvertingEngine(Path(row["embedding_path"]), base_engine=stock_engine))

    if not tiers:
        engine = FallbackNarrationEngine(primary=None, stock=stock_engine)
        engine.fallback_reason = "openvoice_unavailable"
        return engine

    primary = tiers[0] if len(tiers) == 1 else PersonalVoiceChain(tiers)
    return FallbackNarrationEngine(primary=primary, stock=stock_engine)
