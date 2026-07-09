"""Prompt building + the validation gate — specs/03-design/02-script-flow.md.

Validation failure gets exactly one automatic retry with the error fed back
into the prompt; a second failure is honest and final (never a silent loop
that burns quota).
"""
import json
import re
import sqlite3

from pydantic import ValidationError

from app.core.errors import NotFoundError
from app.engines.script_llm import ScriptLLM
from app.models.script import Scene, ScriptContract

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
DIGIT_RE = re.compile(r"[0-9]")
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)

# specs/01-requirements/02-script-generation.md
WORDS_PER_MINUTE = {"en": 140, "hi": 120}
SECONDS_PER_SCENE_MIN = 8
SECONDS_PER_SCENE_MAX = 15

LANGUAGE_NAMES = {"hi": "Hindi", "en": "English"}
SCRIPT_NAMES = {"hi": "Devanagari", "en": "Latin"}


class ScriptValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def target_word_count(language: str, duration_s: int) -> int:
    return round(duration_s / 60 * WORDS_PER_MINUTE[language])


def scene_count_bounds(duration_s: int) -> tuple[int, int]:
    return (
        max(1, duration_s // SECONDS_PER_SCENE_MAX),
        max(1, duration_s // SECONDS_PER_SCENE_MIN),
    )


def build_prompt(description: str, language: str, duration_s: int) -> str:
    words = target_word_count(language, duration_s)
    min_scenes, max_scenes = scene_count_bounds(duration_s)
    language_name = LANGUAGE_NAMES[language]
    script_name = SCRIPT_NAMES[language]
    return f"""You are a professional scriptwriter for short-form narrated video.

Write a scene-segmented narration script for this video idea:
\"\"\"{description}\"\"\"

Rules (follow exactly):
1. Write every "text" field entirely in {language_name}, using {script_name} script. Never romanize, never mix in translation.
2. Target about {words} words total across all scenes ({duration_s} seconds at natural narration pace).
3. Produce between {min_scenes} and {max_scenes} scenes; each scene is 8-15 seconds of narration (roughly one sentence group).
4. The first scene is a hook; the last scene is an outro or call-to-action.
5. Write all numbers as words in {language_name}, never as digits.
6. Never include emoji, markdown, or stage directions in "text" - it is read verbatim by text-to-speech.
7. "visual_hint" is always in English regardless of narration language: 2-5 concrete, photographable keywords for a stock-image search describing that scene's visual.
8. Match the register to the content's implied persona (e.g. an astrologer reading is warm and authoritative; a business explainer is crisp and confident).

Respond with JSON matching the required schema only.
"""


def build_retry_prompt(original_prompt: str, errors: list[str]) -> str:
    error_lines = "\n".join(f"- {e}" for e in errors)
    return f"""{original_prompt}

Your previous response failed validation for these reasons:
{error_lines}

Regenerate the full script, fixing every issue above.
"""


def _validate_scene_text(text: str, language: str) -> list[str]:
    errors = []
    if DIGIT_RE.search(text):
        errors.append(f"scene text contains digits: {text!r} (write numbers as words)")
    if EMOJI_RE.search(text):
        errors.append(f"scene text contains emoji: {text!r}")
    if language == "hi" and not DEVANAGARI_RE.search(text):
        errors.append(f"Hindi scene text is not in Devanagari script (looks romanized): {text!r}")
    return errors


def validate_contract(raw: str, language: str, duration_s: int) -> ScriptContract:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScriptValidationError([f"malformed JSON: {exc}"]) from exc

    try:
        contract = ScriptContract.model_validate(data)
    except ValidationError as exc:
        raise ScriptValidationError([f"schema mismatch: {exc}"]) from exc

    errors: list[str] = []
    if contract.language != language:
        errors.append(f"expected language {language!r}, got {contract.language!r}")

    for scene in contract.scenes:
        errors.extend(_validate_scene_text(scene.text, language))

    min_scenes, max_scenes = scene_count_bounds(duration_s)
    if not (min_scenes <= len(contract.scenes) <= max_scenes):
        errors.append(
            f"scene count {len(contract.scenes)} out of expected range "
            f"[{min_scenes}, {max_scenes}] for a {duration_s}s video"
        )

    if errors:
        raise ScriptValidationError(errors)

    return contract


def generate_script(
    llm: ScriptLLM, description: str, language: str, duration_s: int
) -> ScriptContract:
    prompt = build_prompt(description, language, duration_s)
    raw = llm.generate_raw(prompt)

    try:
        return validate_contract(raw, language, duration_s)
    except ScriptValidationError as first_error:
        retry_prompt = build_retry_prompt(prompt, first_error.errors)
        raw = llm.generate_raw(retry_prompt)
        # A second failure propagates as-is: honest, final, no silent loop.
        return validate_contract(raw, language, duration_s)


# --- Review loop (task-03): manual edit, versioning, duration estimate -----


def estimate_duration_s(scenes: list[Scene], language: str) -> float:
    """specs/03-design/03-review-loop-design.md sticky-footer estimate."""
    word_count = sum(len(scene.text.split()) for scene in scenes)
    return word_count / WORDS_PER_MINUTE[language] * 60


def apply_manual_edit(scenes: list[Scene], scene_id: int, new_text: str) -> list[Scene]:
    """Replace one scene's text; marks it `visual_hint_stale` (regenerated
    lazily at generation time, per specs/01-requirements/03-script-review-loop.md).
    Every other scene comes back byte-identical.
    """
    updated: list[Scene] = []
    found = False
    for scene in scenes:
        if scene.id == scene_id:
            updated.append(
                scene.model_copy(update={"text": new_text, "visual_hint_stale": True})
            )
            found = True
        else:
            updated.append(scene)
    if not found:
        raise NotFoundError(f"Scene {scene_id} not found in this script version")
    return updated


def prune_old_versions(conn: sqlite3.Connection, project_id: str, keep: int = 10) -> None:
    """Keep the most recent `keep` versions (by n); full history beyond that
    is pruned. specs/03-design/03-review-loop-design.md.
    """
    conn.execute(
        """
        DELETE FROM script_versions
        WHERE project_id = ? AND id NOT IN (
            SELECT id FROM script_versions
            WHERE project_id = ?
            ORDER BY n DESC
            LIMIT ?
        )
        """,
        (project_id, project_id, keep),
    )
