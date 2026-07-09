from app.moderation.persona_guard import check_persona_description


def test_generic_role_personas_pass():
    for persona in [
        "wise elderly astrologer",
        "friendly businessman",
        "Indian classical musician",
        "British detective",
        "energetic fitness coach",
    ]:
        assert check_persona_description(persona) is None


def test_look_like_named_person_is_declined():
    assert check_persona_description("make me look like Tom Cruise") is not None


def test_resemble_named_person_is_declined():
    assert check_persona_description("I want to resemble Elon Musk") is not None


def test_dress_as_named_person_is_declined():
    assert check_persona_description("dress up as Albert Einstein") is not None


def test_become_named_person_is_declined():
    assert check_persona_description("become Barack Obama") is not None


def test_as_if_named_person_is_declined():
    assert check_persona_description("as if I'm Taylor Swift") is not None


def test_single_name_mononyms_are_not_caught():
    """A known scope limitation, documented in persona_guard.py's own
    docstring: this heuristic requires a 2+ word capitalized sequence, so
    single-name impersonation attempts slip through. Locked in as a test
    so the gap stays visible rather than silently assumed fixed."""
    assert check_persona_description("look like Madonna") is None
