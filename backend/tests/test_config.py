from pathlib import Path

from app.core.config import Settings, get_settings


def test_defaults_have_no_keys_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key is None
    assert settings.pexels_api_key is None
    assert settings.pixabay_api_key is None


def test_env_vars_are_picked_up(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test")
    monkeypatch.setenv("PEXELS_API_KEY", "pk-test")
    monkeypatch.setenv("PIXABAY_API_KEY", "pb-test")
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key == "gk-test"
    assert settings.pexels_api_key == "pk-test"
    assert settings.pixabay_api_key == "pb-test"


def test_media_root_and_db_path_are_paths():
    settings = Settings(_env_file=None)
    assert isinstance(settings.media_root, Path)
    assert isinstance(settings.db_path, Path)
    assert settings.db_path.suffix == ".db"


def test_voice_table_matches_locked_spec():
    # specs/01-requirements/06-languages-hindi-english.md
    settings = Settings(_env_file=None)
    assert settings.voice_table == {
        "hi": {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"},
        "en": {"female": "en-IN-NeerjaNeural", "male": "en-IN-PrabhatNeural"},
        "en-US": {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"},
    }


def test_voice_table_has_two_voices_per_language():
    settings = Settings(_env_file=None)
    for language, voices in settings.voice_table.items():
        assert set(voices.keys()) == {"female", "male"}, language


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
