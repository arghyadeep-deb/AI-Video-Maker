"""AI improve-selection — specs/03-design/03-review-loop-design.md.

`start`/`end` are Unicode codepoint offsets into the scene's `text`. Python
strings index by codepoint natively, so `text[start:end]` is already
correct; the frontend is responsible for converting DOM (UTF-16) selection
offsets into codepoints before this ever sees them.
"""
from app.core.errors import AppError, NotFoundError
from app.engines.script_llm import ScriptLLM
from app.models.script import Scene

LANGUAGE_NAMES = {"hi": "Hindi", "en": "English"}


class InvalidSpanError(AppError):
    code = "invalid_span"


def find_scene(scenes: list[Scene], scene_id: int) -> Scene:
    scene = next((s for s in scenes if s.id == scene_id), None)
    if scene is None:
        raise NotFoundError(f"Scene {scene_id} not found in this script version")
    return scene


def extract_span(scene: Scene, start: int, end: int) -> str:
    text = scene.text
    if not (0 <= start < end <= len(text)):
        raise InvalidSpanError(
            f"span [{start}, {end}) out of bounds for scene text of length {len(text)}"
        )
    return text[start:end]


def splice_span(scene_text: str, start: int, end: int, replacement: str) -> str:
    """Replace scene_text[start:end] with `replacement`. Belt-and-braces
    assertion (per task-04's Implementation notes): everything outside the
    selected span must survive byte-identical.
    """
    prefix = scene_text[:start]
    suffix = scene_text[end:]
    result = prefix + replacement + suffix
    assert result.startswith(prefix), "splice must not alter text before the span"
    assert result.endswith(suffix) or not suffix, "splice must not alter text after the span"
    return result


def build_improve_prompt(
    scenes: list[Scene],
    scene_id: int,
    span: str,
    instruction: str | None,
    language: str,
) -> str:
    language_name = LANGUAGE_NAMES[language]
    full_script = "\n".join(f"Scene {s.id}: {s.text}" for s in scenes)
    instruction_line = (
        f'Specific instruction: "{instruction}"'
        if instruction
        else "No specific instruction beyond making it better."
    )
    return f"""You are improving one small part of an existing narration script. Full script for context:

{full_script}

The user selected this exact span from scene {scene_id}:
\"\"\"{span}\"\"\"

{instruction_line}

Rules (follow exactly):
1. Return ONLY the replacement text for the selected span - nothing before or after it, no quotes, no explanation, no extra sentences.
2. Write it entirely in {language_name}, using the same script as the original (never romanize, never translate).
3. Keep a similar length to the original unless the instruction explicitly asks for more or less.
4. No digits (write numbers as words), no emoji, no markdown, no stage directions - read verbatim by text-to-speech.
5. Match the tone and register of the surrounding script.
"""


def make_proposal(
    llm: ScriptLLM,
    scenes: list[Scene],
    scene_id: int,
    start: int,
    end: int,
    instruction: str | None,
    language: str,
) -> tuple[str, str, str]:
    """Returns (old_span, new_span, proposed_scene_text)."""
    scene = find_scene(scenes, scene_id)
    old_span = extract_span(scene, start, end)
    prompt = build_improve_prompt(scenes, scene_id, old_span, instruction, language)
    new_span = llm.generate_text(prompt).strip()
    proposed_scene_text = splice_span(scene.text, start, end, new_span)
    return old_span, new_span, proposed_scene_text
