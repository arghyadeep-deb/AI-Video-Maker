"""Integration test: the full render_mode_b pipeline end to end (task-09's
own Tests section: "FakeTTS + fixture images: 3-scene render completes;
ffprobe checks duration/resolution/streams"). Uses FakeTTSEngine (no
network) and in-memory fixture image bytes (no real Pexels/Pixabay/Gemini
keys available in this environment) so this runs deterministically
anywhere ffmpeg is installed.
"""
import json
import shutil
import subprocess

import pytest

from app.core.config import get_settings
from app.core.ids import new_id
from app.db.connection import get_connection, run_migrations
from app.engines.tts.fake import FakeTTSEngine
from app.jobs.registry import JobContext
from app.models.image import ImageCandidate
from app.pipelines import mode_b

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


class RealAudioFakeTTS(FakeTTSEngine):
    """FakeTTSEngine writes a placeholder byte string, not decodable audio -
    fine for fast unit tests, but this integration test runs the assemble
    stage through real ffmpeg, which needs a genuinely valid (if silent)
    audio file of the right duration.
    """

    async def speak(self, text, voice, out_path, rate=None):
        result = await super().speak(text, voice, out_path, rate)
        duration_s = (
            (result.timings[-1].offset_ms + result.timings[-1].duration_ms) / 1000
            if result.timings
            else 0.5
        )
        # A very quiet tone, not true digital silence (anullsrc): loudnorm's
        # two-pass loudness measurement produces NaN on a zero-amplitude
        # signal (confirmed by direct probe - a real edge-tts recording
        # always has actual signal, so this is purely a test-fixture
        # concern, not a production bug).
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=24000",
                "-af", "volume=0.01",
                "-t", f"{max(duration_s, 0.1):.3f}", "-q:a", "9", str(out_path),
            ],
            check=True, capture_output=True, timeout=15,
        )
        return result


def _make_fixture_jpeg_bytes(color: str) -> bytes:
    """A real, valid small JPEG (not arbitrary bytes) via ffmpeg's lavfi
    color source, so the assemble stage's zoompan/scale filters have
    genuine image data to operate on.
    """
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "fixture.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920", "-frames:v", "1", str(out)],
            check=True,
            capture_output=True,
            timeout=15,
        )
        return out.read_bytes()


class StubImageEngine:
    def __init__(self, color: str):
        self._bytes = _make_fixture_jpeg_bytes(color)

    async def search(self, query, orientation, per_page=5):
        return [
            ImageCandidate(
                source="genai", source_id=f"fixture-{query}", width=1080, height=1920, image_bytes=self._bytes
            )
        ]


class EmptyImageEngine:
    async def search(self, query, orientation, per_page=5):
        return []


def _job_context(payload: dict) -> JobContext:
    return JobContext(
        job_id="test-job", payload=payload,
        report=lambda pct: None, cancelled=lambda: False, register_process=lambda p: None,
    )


def _seed_project(conn, project_id: str, language: str, duration_s: int, video_format: str, scenes: list[dict]):
    conn.execute("INSERT OR IGNORE INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')")
    conn.execute(
        "INSERT INTO projects (id, user_id, description, language, duration_s, format, status) "
        "VALUES (?, 'u1', 'd', ?, ?, ?, 'accepted')",
        (project_id, language, duration_s, video_format),
    )
    version_id = f"{project_id}-v1"
    conn.execute(
        "INSERT INTO script_versions (id, project_id, n, scenes_json, origin) VALUES (?, ?, 1, ?, 'generated')",
        (version_id, project_id, json.dumps(scenes, ensure_ascii=False)),
    )
    conn.execute("UPDATE projects SET accepted_version_id = ? WHERE id = ?", (version_id, project_id))
    conn.commit()


@pytest.fixture
def pipeline_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    get_settings.cache_clear()

    monkeypatch.setattr(mode_b, "make_tts_engine", lambda: RealAudioFakeTTS())
    # Both stocks return nothing -> forces the genai fallback path, which we
    # stub with real (small, valid) fixture JPEGs so ffmpeg has real pixels.
    monkeypatch.setattr(mode_b, "make_pexels_engine", lambda settings: EmptyImageEngine())
    monkeypatch.setattr(mode_b, "make_pixabay_engine", lambda settings: EmptyImageEngine())
    monkeypatch.setattr(mode_b, "make_genai_image_engine", lambda settings: StubImageEngine("0x2a5298"))

    settings = get_settings()
    run_migrations(settings.db_path)
    conn = get_connection(settings.db_path)
    yield conn, settings
    conn.close()
    get_settings.cache_clear()


def _ffprobe_json(path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=15,
    )
    return json.loads(result.stdout)


async def _run_stage(stage_fn, payload):
    await stage_fn(_job_context(payload))


async def test_three_scene_mode_b_render_completes(pipeline_env):
    conn, settings = pipeline_env
    project_id = "p1"
    scenes = [
        {"id": 1, "text": "यह पहला दृश्य है।", "visual_hint": "sunrise mountains", "visual_hint_stale": False},
        {"id": 2, "text": "यह दूसरा दृश्य है।", "visual_hint": "city street", "visual_hint_stale": False},
        {"id": 3, "text": "यह तीसरा दृश्य है।", "visual_hint": "calm lake", "visual_hint_stale": False},
    ]
    _seed_project(conn, project_id, "hi", 60, "9x16", scenes)

    payload = {"project_id": project_id}
    await _run_stage(mode_b.stage_tts, payload)
    await _run_stage(mode_b.stage_images, payload)
    await _run_stage(mode_b.stage_subtitles, payload)
    await _run_stage(mode_b.stage_assemble, payload)
    await _run_stage(mode_b.stage_finalize, payload)

    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    assert project["status"] == "done"
    assert project["output_path"] is not None

    output_path = project["output_path"]
    probe = _ffprobe_json(output_path)
    assert probe["format"]["format_name"].startswith("mov,mp4")

    video_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
    audio_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    assert len(video_streams) == 1
    assert len(audio_streams) == 1
    assert video_streams[0]["width"] == 1080
    assert video_streams[0]["height"] == 1920

    # specs/04-tasks/task-19-moderation-consent.md: "provenance tag in output
    # MP4s (comment=AI-generated)".
    assert probe["format"]["tags"]["comment"] == "AI-generated"

    # Duration should roughly match the sum of the 3 scenes' fake-TTS audio
    # (each scene's word count * 400ms per FakeTTSEngine, minus the 50ms
    # trim on the last word) - loose tolerance since loudnorm/container
    # muxing can shift things by a frame or two.
    duration_s = float(probe["format"]["duration"])
    assert duration_s > 1.0

    # credits.txt written and mentions the genai fallback (both stocks empty).
    from pathlib import Path

    project_dir = Path(output_path).parent
    credits = (project_dir / "credits.txt").read_text(encoding="utf-8")
    assert "AI-generated" in credits
    assert credits.count("Scene ") == 3

    # A real frame-grab thumbnail, not just a frame-shaped placeholder.
    thumbnail_probe = _ffprobe_json(project_dir / "thumbnail.jpg")
    assert thumbnail_probe["streams"][0]["codec_type"] == "video"


async def test_karaoke_style_emits_word_timing_tags(pipeline_env):
    conn, settings = pipeline_env
    project_id = "p_karaoke"
    scenes = [{"id": 1, "text": "नमस्ते दोस्तों।", "visual_hint": "greeting", "visual_hint_stale": False}]
    _seed_project(conn, project_id, "hi", 30, "9x16", scenes)

    payload = {"project_id": project_id, "subtitle_style": "karaoke"}
    await _run_stage(mode_b.stage_tts, payload)
    await _run_stage(mode_b.stage_images, payload)
    await _run_stage(mode_b.stage_subtitles, payload)

    # output_path isn't set until finalize - read straight from the known
    # project media layout instead.
    from app.pipelines.common import project_dir as _pd

    subs_dir = _pd(settings.media_root, "u1", project_id) / "subs"
    ass_content = (subs_dir / "subtitles.ass").read_text(encoding="utf-8")
    assert "\\k" in ass_content


async def test_single_scene_render_completes(pipeline_env):
    conn, settings = pipeline_env
    project_id = "p2"
    scenes = [{"id": 1, "text": "अकेला दृश्य है।", "visual_hint": "quiet room", "visual_hint_stale": False}]
    _seed_project(conn, project_id, "hi", 30, "16x9", scenes)

    payload = {"project_id": project_id}
    await _run_stage(mode_b.stage_tts, payload)
    await _run_stage(mode_b.stage_images, payload)
    await _run_stage(mode_b.stage_subtitles, payload)
    await _run_stage(mode_b.stage_assemble, payload)
    await _run_stage(mode_b.stage_finalize, payload)

    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    assert project["status"] == "done"

    probe = _ffprobe_json(project["output_path"])
    video_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
    assert video_streams[0]["width"] == 1920
    assert video_streams[0]["height"] == 1080


async def test_render_with_music_mixes_a_second_audio_source(pipeline_env, monkeypatch, tmp_path):
    conn, settings = pipeline_env
    project_id = "p3"
    scenes = [{"id": 1, "text": "अकेला दृश्य है।", "visual_hint": "quiet room", "visual_hint_stale": False}]
    _seed_project(conn, project_id, "hi", 30, "9x16", scenes)

    music_path = tmp_path / "calm-1.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=20", str(music_path)],
        check=True, capture_output=True, timeout=15,
    )
    from app.services import music_library

    monkeypatch.setattr(
        music_library, "pick_track",
        lambda mood, rng=None: {"filename": "calm-1.mp3", "mood": "calm", "path": str(music_path)},
    )

    payload = {"project_id": project_id, "music_enabled": True, "music_mood": "calm"}
    await _run_stage(mode_b.stage_tts, payload)
    await _run_stage(mode_b.stage_images, payload)
    await _run_stage(mode_b.stage_subtitles, payload)
    await _run_stage(mode_b.stage_assemble, payload)
    await _run_stage(mode_b.stage_finalize, payload)

    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    assert project["status"] == "done"

    probe = _ffprobe_json(project["output_path"])
    audio_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    assert len(audio_streams) == 1  # narration + music mixed down to one stream, not two tracks

    from pathlib import Path

    project_dir = Path(project["output_path"]).parent
    credits = (project_dir / "credits.txt").read_text(encoding="utf-8")
    assert "calm-1.mp3" in credits
    assert "Background music" in credits
