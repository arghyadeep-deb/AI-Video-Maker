import json
import random

from app.services import music_library


def _write_manifest(tmp_path, monkeypatch, tracks):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(tracks), encoding="utf-8")
    monkeypatch.setattr(music_library, "MUSIC_DIR", tmp_path)
    monkeypatch.setattr(music_library, "MANIFEST_PATH", manifest_path)
    for track in tracks:
        (tmp_path / track["filename"]).write_bytes(b"fake-audio-bytes")


def test_load_manifest_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(music_library, "MANIFEST_PATH", tmp_path / "does-not-exist.json")
    assert music_library.load_manifest() == []


def test_pick_track_returns_none_for_an_unknown_mood(tmp_path, monkeypatch):
    _write_manifest(
        tmp_path, monkeypatch,
        [{"filename": "a.mp3", "mood": "calm", "duration_s": 60}],
    )
    assert music_library.pick_track("upbeat") is None


def test_pick_track_returns_a_matching_track(tmp_path, monkeypatch):
    _write_manifest(
        tmp_path, monkeypatch,
        [
            {"filename": "calm-1.mp3", "mood": "calm", "duration_s": 60},
            {"filename": "upbeat-1.mp3", "mood": "upbeat", "duration_s": 90},
        ],
    )
    track = music_library.pick_track("calm")
    assert track is not None
    assert track["filename"] == "calm-1.mp3"
    assert track["path"].endswith("calm-1.mp3")


def test_pick_track_ignores_manifest_entries_whose_file_is_missing(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps([{"filename": "ghost.mp3", "mood": "calm", "duration_s": 60}]), encoding="utf-8"
    )
    monkeypatch.setattr(music_library, "MUSIC_DIR", tmp_path)
    monkeypatch.setattr(music_library, "MANIFEST_PATH", manifest_path)
    # ghost.mp3 deliberately never written to disk.
    assert music_library.pick_track("calm") is None


def test_pick_track_is_random_among_matches(tmp_path, monkeypatch):
    _write_manifest(
        tmp_path, monkeypatch,
        [
            {"filename": "calm-1.mp3", "mood": "calm", "duration_s": 60},
            {"filename": "calm-2.mp3", "mood": "calm", "duration_s": 60},
        ],
    )
    seen = {music_library.pick_track("calm", rng=random.Random(seed))["filename"] for seed in range(20)}
    assert seen == {"calm-1.mp3", "calm-2.mp3"}


def test_available_moods_lists_distinct_moods(tmp_path, monkeypatch):
    _write_manifest(
        tmp_path, monkeypatch,
        [
            {"filename": "a.mp3", "mood": "calm", "duration_s": 60},
            {"filename": "b.mp3", "mood": "calm", "duration_s": 60},
            {"filename": "c.mp3", "mood": "upbeat", "duration_s": 60},
        ],
    )
    assert music_library.available_moods() == ["calm", "upbeat"]
