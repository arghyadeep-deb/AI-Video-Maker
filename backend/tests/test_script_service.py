import pytest

from app.services.script_service import (
    ScriptValidationError,
    build_prompt,
    generate_script,
    scene_count_bounds,
    validate_contract,
)


def _contract_json(language="hi", scenes=None):
    import json

    if scenes is None:
        scenes = [
            {"id": 1, "text": "नमस्ते दोस्तों, आज हम बात करेंगे।", "visual_hint": "friendly greeting"},
            {"id": 2, "text": "यह एक बहुत अच्छा विचार है।", "visual_hint": "lightbulb idea"},
        ]
    return json.dumps({"title": "Test", "language": language, "scenes": scenes})


class FakeLLM:
    """Returns canned responses in order; records prompts it was called with."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate_raw(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0)


def test_build_prompt_contains_language_directive():
    prompt = build_prompt("business tips", "hi", 60)
    assert "Hindi" in prompt
    assert "Devanagari" in prompt


def test_build_prompt_contains_english_directive():
    prompt = build_prompt("business tips", "en", 60)
    assert "English" in prompt
    assert "Latin" in prompt


def test_scene_count_bounds():
    assert scene_count_bounds(60) == (4, 7)
    assert scene_count_bounds(30) == (2, 3)


def test_build_prompt_is_explicit_about_literal_field_formats():
    """Regression: the LLM was writing language="English" (the display name)
    instead of "en", and scene ids as words ("One") instead of integers -
    live-caught 422s, both fields' rule 5 phrasing was ambiguous about
    whether "numbers as words" applied to the JSON structure itself."""
    prompt = build_prompt("business tips", "en", 60)
    assert 'the literal string "en"' in prompt
    assert "never a word like" in prompt
    assert "applies ONLY to narrated prose" in prompt


def test_validate_contract_accepts_good_hindi():
    contract = validate_contract(_contract_json(), "hi", 30)
    assert contract.language == "hi"
    assert len(contract.scenes) == 2


def test_validate_contract_rejects_romanized_hindi():
    scenes = [
        {"id": 1, "text": "Namaste dosto, aaj hum baat karenge", "visual_hint": "greeting"},
        {"id": 2, "text": "Yeh ek accha vichar hai", "visual_hint": "idea"},
    ]
    with pytest.raises(ScriptValidationError) as exc_info:
        validate_contract(_contract_json(scenes=scenes), "hi", 30)
    assert any("romanized" in e for e in exc_info.value.errors)


def test_validate_contract_rejects_digits():
    scenes = [
        {"id": 1, "text": "हमें 5 टिप्स चाहिए", "visual_hint": "tips"},
        {"id": 2, "text": "यह एक बहुत अच्छा विचार है।", "visual_hint": "idea"},
    ]
    with pytest.raises(ScriptValidationError) as exc_info:
        validate_contract(_contract_json(scenes=scenes), "hi", 30)
    assert any("digits" in e for e in exc_info.value.errors)


def test_validate_contract_rejects_emoji():
    scenes = [
        {"id": 1, "text": "नमस्ते दोस्तों 🎉", "visual_hint": "greeting"},
        {"id": 2, "text": "यह एक बहुत अच्छा विचार है।", "visual_hint": "idea"},
    ]
    with pytest.raises(ScriptValidationError) as exc_info:
        validate_contract(_contract_json(scenes=scenes), "hi", 30)
    assert any("emoji" in e for e in exc_info.value.errors)


def test_validate_contract_rejects_wrong_language():
    with pytest.raises(ScriptValidationError) as exc_info:
        validate_contract(_contract_json(language="en"), "hi", 30)
    assert any("expected language" in e for e in exc_info.value.errors)


def test_validate_contract_rejects_malformed_json():
    with pytest.raises(ScriptValidationError) as exc_info:
        validate_contract("not json", "hi", 30)
    assert any("malformed JSON" in e for e in exc_info.value.errors)


def test_validate_contract_rejects_bad_scene_count():
    scenes = [{"id": 1, "text": "नमस्ते दोस्तों।", "visual_hint": "greeting"}]
    with pytest.raises(ScriptValidationError) as exc_info:
        validate_contract(_contract_json(scenes=scenes), "hi", 300)
    assert any("scene count" in e for e in exc_info.value.errors)


def test_generate_script_succeeds_first_try():
    llm = FakeLLM([_contract_json()])
    contract = generate_script(llm, "some topic", "hi", 30)
    assert contract.title == "Test"
    assert len(llm.prompts) == 1


def test_generate_script_retries_once_then_succeeds():
    bad = _contract_json(
        scenes=[
            {"id": 1, "text": "Namaste", "visual_hint": "x"},
            {"id": 2, "text": "Dosto", "visual_hint": "y"},
        ]
    )
    good = _contract_json()
    llm = FakeLLM([bad, good])
    contract = generate_script(llm, "some topic", "hi", 30)
    assert contract.language == "hi"
    assert len(llm.prompts) == 2
    assert "failed validation" in llm.prompts[1]


def test_generate_script_fails_honestly_after_one_retry():
    bad = _contract_json(
        scenes=[
            {"id": 1, "text": "Namaste", "visual_hint": "x"},
            {"id": 2, "text": "Dosto", "visual_hint": "y"},
        ]
    )
    llm = FakeLLM([bad, bad])
    with pytest.raises(ScriptValidationError):
        generate_script(llm, "some topic", "hi", 30)
    assert len(llm.prompts) == 2
