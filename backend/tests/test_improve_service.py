import pytest

from app.core.errors import NotFoundError
from app.models.script import Scene
from app.services.improve_service import (
    InvalidSpanError,
    build_improve_prompt,
    extract_span,
    find_scene,
    make_proposal,
    splice_span,
)


def _scenes():
    return [
        Scene(id=1, text="नमस्ते दोस्तों, आज हम बात करेंगे।", visual_hint="greeting"),
        Scene(id=2, text="यह एक बहुत अच्छा विचार है।", visual_hint="idea"),
    ]


class FakeTextLLM:
    def __init__(self, response: str):
        self._response = response
        self.prompts: list[str] = []

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._response


def test_find_scene_returns_match():
    scene = find_scene(_scenes(), 2)
    assert scene.id == 2


def test_find_scene_raises_not_found():
    with pytest.raises(NotFoundError):
        find_scene(_scenes(), 99)


def test_extract_span_returns_exact_substring():
    scene = Scene(id=1, text="नमस्ते दोस्तों", visual_hint="x")
    # "दोस्तों" starts right after "नमस्ते " (7 codepoints incl. space)
    span = extract_span(scene, 7, len(scene.text))
    assert span == "दोस्तों"


def test_extract_span_rejects_out_of_bounds():
    scene = Scene(id=1, text="hello", visual_hint="x")
    with pytest.raises(InvalidSpanError):
        extract_span(scene, 3, 999)
    with pytest.raises(InvalidSpanError):
        extract_span(scene, 5, 2)  # start >= end


def test_splice_span_preserves_prefix_and_suffix():
    result = splice_span("abcXYZdef", 3, 6, "123")
    assert result == "abc123def"


def test_splice_span_at_start():
    result = splice_span("XYZdef", 0, 3, "abc")
    assert result == "abcdef"


def test_splice_span_at_end():
    result = splice_span("abcXYZ", 3, 6, "def")
    assert result == "abcdef"


def test_splice_span_devanagari_conjunct_heavy():
    # Conjunct clusters (e.g. क्ष, ज्ञ) are still just sequences of
    # codepoints in Python str - splice must work at any codepoint boundary.
    text = "विशेष ज्ञान महत्वपूर्ण है।"
    start = text.index("ज्ञान")
    end = start + len("ज्ञान")
    result = splice_span(text, start, end, "जानकारी")
    assert result == "विशेष जानकारी महत्वपूर्ण है।"


def test_build_improve_prompt_contains_span_and_instruction():
    prompt = build_improve_prompt(_scenes(), 1, "आज हम बात करेंगे", "make it funnier", "hi")
    assert "आज हम बात करेंगे" in prompt
    assert "make it funnier" in prompt
    assert "Hindi" in prompt


def test_make_proposal_returns_old_new_and_spliced_text():
    scenes = _scenes()
    scene = scenes[0]
    start = scene.text.index("आज")
    end = start + len("आज हम बात करेंगे")
    llm = FakeTextLLM("अभी हम चर्चा करेंगे")

    old_span, new_span, proposed = make_proposal(llm, scenes, 1, start, end, None, "hi")

    assert old_span == "आज हम बात करेंगे"
    assert new_span == "अभी हम चर्चा करेंगे"
    assert proposed == scene.text[:start] + "अभी हम चर्चा करेंगे" + scene.text[end:]
    # Other scene must be untouched (same object, never passed to splice).
    assert scenes[1].text == "यह एक बहुत अच्छा विचार है।"


def test_make_proposal_unknown_scene_raises_not_found():
    llm = FakeTextLLM("x")
    with pytest.raises(NotFoundError):
        make_proposal(llm, _scenes(), 999, 0, 1, None, "hi")
