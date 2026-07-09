"""Shared helpers between render_mode_a and render_mode_b —
specs/03-design/08-data-model.md's project directory layout and the
accepted-script-version lookup both pipelines need identically.
"""
import json
from pathlib import Path
from typing import Optional

from app.core.errors import NotFoundError
from app.engines.tts.base import SpeechResult, TTSEngine
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
    Tries the personal (OpenVoice-converted) engine first when the user
    has one; falls back to the stock engine on ANY conversion failure,
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
        from app.engines.tts.openvoice import OpenVoiceUnavailableError

        if self._primary is not None:
            try:
                result = await self._primary.speak(text, voice, out_path, rate)
                self.used_stock_fallback = False
                self.fallback_reason = None
                return result
            except OpenVoiceUnavailableError as exc:
                self.used_stock_fallback = True
                self.fallback_reason = str(exc)
        return await self._stock.speak(text, voice, out_path, rate)


def make_narration_engine(conn, user_id: str, stock_engine: TTSEngine) -> FallbackNarrationEngine:
    """Looks up the user's enrolled ('cloned') voice profile, if any, and
    wraps it with the honest stock-voice fallback above."""
    row = conn.execute(
        "SELECT * FROM voice_profiles WHERE user_id = ? AND kind = 'cloned'", (user_id,)
    ).fetchone()
    if row is None:
        return FallbackNarrationEngine(primary=None, stock=stock_engine)

    from app.engines.tts.openvoice import OpenVoiceConvertingEngine, is_available

    if not is_available():
        engine = FallbackNarrationEngine(primary=None, stock=stock_engine)
        engine.fallback_reason = "openvoice_unavailable"
        return engine

    primary = OpenVoiceConvertingEngine(Path(row["embedding_path"]), base_engine=stock_engine)
    return FallbackNarrationEngine(primary=primary, stock=stock_engine)
