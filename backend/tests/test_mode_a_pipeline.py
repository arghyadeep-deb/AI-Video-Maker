"""Integration test: the full render_mode_a pipeline end to end (task-12's
own Tests section: "Integration (FakeTTS + stub animator): full pipeline to
a playable mp4; subtitles toggle honored"). Uses FakeTTSEngine (no network)
and a stub talking-head engine that produces a real (if trivial) video via
ffmpeg, so this runs deterministically anywhere ffmpeg is installed - no
real Wav2Lip/SadTalker weights needed for this test (those are covered by
task-11's own real Wav2Lip integration test).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.db.connection import get_connection, run_migrations
from app.engines.talking_head.base import TalkingHeadResult
from app.engines.tts.fake import FakeTTSEngine
from app.jobs.registry import JobContext
from app.pipelines import mode_a

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


class RealAudioFakeTTS(FakeTTSEngine):
    """Same rationale as test_mode_b_pipeline.py's own class: FakeTTSEngine's
    placeholder bytes aren't decodable, but this test runs real ffmpeg."""

    async def speak(self, text, voice, out_path, rate=None):
        result = await super().speak(text, voice, out_path, rate)
        duration_s = (
            (result.timings[-1].offset_ms + result.timings[-1].duration_ms) / 1000
            if result.timings
            else 0.5
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=24000",
                "-af", "volume=0.01",
                "-t", f"{max(duration_s, 0.1):.3f}", "-q:a", "9", str(out_path),
            ],
            check=True, capture_output=True, timeout=15,
        )
        return result


class StubTalkingHeadEngine:
    """Stands in for Wav2Lip/SadTalker: produces a real, small, playable MP4
    (matching the avatar portrait's own square dimensions, and the input
    WAV's duration) via ffmpeg's lavfi sources - no real lip-sync model
    needed to exercise the rest of the pipeline (scale/pad, subtitle burn,
    loudnorm)."""

    async def render(self, portrait_path, wav_path, output_path):
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(wav_path)],
            capture_output=True, text=True, timeout=10, check=True,
        )
        duration_s = float(probe.stdout.strip())
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=0x445566:s=1024x1024:d={max(duration_s, 0.1):.3f}",
                "-i", str(wav_path),
                "-shortest", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac",
                str(output_path),
            ],
            check=True, capture_output=True, timeout=30,
        )
        return TalkingHeadResult(video_path=str(output_path), engine="wav2lip")


def _make_test_portrait(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0xb8860b:s=1024x1024", "-frames:v", "1", str(path)],
        check=True, capture_output=True, timeout=15,
    )


def _job_context(payload: dict) -> JobContext:
    return JobContext(
        job_id="test-job", payload=payload,
        report=lambda pct: None, cancelled=lambda: False, register_process=lambda p: None,
    )


def _seed_project_and_avatar(conn, project_id: str, avatar_id: str, portrait_path: Path,
                              language: str, duration_s: int, video_format: str, scenes: list[dict]):
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
    conn.execute(
        "INSERT INTO avatars (id, user_id, name, persona_description, selfie_path, portrait_path, "
        "approved, consented) VALUES (?, 'u1', 'Test', 'Astrologer', ?, ?, 1, 1)",
        (avatar_id, str(portrait_path), str(portrait_path)),
    )
    conn.commit()


@pytest.fixture
def pipeline_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    get_settings.cache_clear()

    monkeypatch.setattr(mode_a, "make_tts_engine", lambda: RealAudioFakeTTS())
    monkeypatch.setattr(mode_a, "make_wav2lip_engine", lambda: StubTalkingHeadEngine())
    monkeypatch.setattr(mode_a, "make_sadtalker_engine", lambda settings, conn: None)

    settings = get_settings()
    run_migrations(settings.db_path)
    conn = get_connection(settings.db_path)
    yield conn, settings, tmp_path
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


async def test_mode_a_render_completes_with_subtitles(pipeline_env):
    conn, settings, tmp_path = pipeline_env
    project_id = "p1"
    avatar_id = "av1"
    portrait_path = tmp_path / "portrait.png"
    _make_test_portrait(portrait_path)

    scenes = [
        {"id": 1, "text": "नमस्ते दोस्तों, आज हम बात करेंगे।", "visual_hint": "greeting", "visual_hint_stale": False},
        {"id": 2, "text": "धन्यवाद, फिर मिलेंगे।", "visual_hint": "goodbye", "visual_hint_stale": False},
    ]
    _seed_project_and_avatar(conn, project_id, avatar_id, portrait_path, "hi", 30, "9x16", scenes)

    payload = {"project_id": project_id, "avatar_id": avatar_id, "subtitles": True}
    await _run_stage(mode_a.stage_tts, payload)
    await _run_stage(mode_a.stage_animate, payload)
    await _run_stage(mode_a.stage_assemble, payload)

    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    assert project["status"] == "done"
    assert project["output_path"] is not None

    probe = _ffprobe_json(project["output_path"])
    assert probe["format"]["format_name"].startswith("mov,mp4")
    video_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
    audio_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    assert len(video_streams) == 1
    assert len(audio_streams) == 1
    # 1024x1024 square avatar into a 9:16 target - cover-crop, no padding.
    assert video_streams[0]["width"] == 1080
    assert video_streams[0]["height"] == 1920

    # specs/04-tasks/task-19-moderation-consent.md: "provenance tag in output
    # MP4s (comment=AI-generated)".
    assert probe["format"]["tags"]["comment"] == "AI-generated"

    project_dir = Path(project["output_path"]).parent
    assert (project_dir / "subs" / "subtitles.ass").exists()
    assert (project_dir / "subs" / "subtitles.srt").exists()

    # Mode A's thumbnail is the avatar's own portrait, not a frame-grab.
    assert (project_dir / "thumbnail.jpg").read_bytes() == portrait_path.read_bytes()


async def test_mode_a_karaoke_style_emits_word_timing_tags(pipeline_env):
    conn, settings, tmp_path = pipeline_env
    project_id = "p_karaoke"
    avatar_id = "av_karaoke"
    portrait_path = tmp_path / "portrait.png"
    _make_test_portrait(portrait_path)

    scenes = [{"id": 1, "text": "नमस्ते दोस्तों।", "visual_hint": "greeting", "visual_hint_stale": False}]
    _seed_project_and_avatar(conn, project_id, avatar_id, portrait_path, "hi", 30, "9x16", scenes)

    payload = {
        "project_id": project_id, "avatar_id": avatar_id,
        "subtitles": True, "subtitle_style": "karaoke",
    }
    await _run_stage(mode_a.stage_tts, payload)
    await _run_stage(mode_a.stage_animate, payload)
    await _run_stage(mode_a.stage_assemble, payload)

    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project_dir = Path(project["output_path"]).parent
    ass_content = (project_dir / "subs" / "subtitles.ass").read_text(encoding="utf-8")
    assert "\\k" in ass_content


async def test_mode_a_subtitles_toggle_off_skips_subtitle_files(pipeline_env):
    conn, settings, tmp_path = pipeline_env
    project_id = "p2"
    avatar_id = "av2"
    portrait_path = tmp_path / "portrait.png"
    _make_test_portrait(portrait_path)

    scenes = [{"id": 1, "text": "अकेला दृश्य है।", "visual_hint": "quiet room", "visual_hint_stale": False}]
    _seed_project_and_avatar(conn, project_id, avatar_id, portrait_path, "hi", 30, "16x9", scenes)

    payload = {"project_id": project_id, "avatar_id": avatar_id, "subtitles": False}
    await _run_stage(mode_a.stage_tts, payload)
    await _run_stage(mode_a.stage_animate, payload)
    await _run_stage(mode_a.stage_assemble, payload)

    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    assert project["status"] == "done"

    project_dir = Path(project["output_path"]).parent
    assert not (project_dir / "subs" / "subtitles.ass").exists()

    probe = _ffprobe_json(project["output_path"])
    video_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
    assert video_streams[0]["width"] == 1920
    assert video_streams[0]["height"] == 1080


async def test_mode_a_records_which_engine_rendered(pipeline_env):
    conn, settings, tmp_path = pipeline_env
    project_id = "p3"
    avatar_id = "av3"
    portrait_path = tmp_path / "portrait.png"
    _make_test_portrait(portrait_path)

    scenes = [{"id": 1, "text": "अकेला दृश्य है।", "visual_hint": "quiet room", "visual_hint_stale": False}]
    _seed_project_and_avatar(conn, project_id, avatar_id, portrait_path, "hi", 30, "9x16", scenes)

    conn.execute(
        "INSERT INTO jobs (id, user_id, project_id, type, status, payload_json) "
        "VALUES ('test-job', 'u1', ?, 'render_mode_a', 'running', '{}')",
        (project_id,),
    )
    conn.commit()

    payload = {"project_id": project_id, "avatar_id": avatar_id, "subtitles": True}
    await _run_stage(mode_a.stage_tts, payload)
    await _run_stage(mode_a.stage_animate, payload)

    job = conn.execute("SELECT engine_notes FROM jobs WHERE id = 'test-job'").fetchone()
    assert job["engine_notes"] == "wav2lip"


async def test_mode_a_render_with_music_mixes_a_second_audio_source(pipeline_env, monkeypatch):
    conn, settings, tmp_path = pipeline_env
    project_id = "p_music"
    avatar_id = "av_music"
    portrait_path = tmp_path / "portrait.png"
    _make_test_portrait(portrait_path)

    scenes = [{"id": 1, "text": "अकेला दृश्य है।", "visual_hint": "quiet room", "visual_hint_stale": False}]
    _seed_project_and_avatar(conn, project_id, avatar_id, portrait_path, "hi", 30, "9x16", scenes)

    music_path = tmp_path / "upbeat-1.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=20", str(music_path)],
        check=True, capture_output=True, timeout=15,
    )
    from app.services import music_library

    monkeypatch.setattr(
        music_library, "pick_track",
        lambda mood, rng=None: {"filename": "upbeat-1.mp3", "mood": "upbeat", "path": str(music_path)},
    )

    payload = {
        "project_id": project_id, "avatar_id": avatar_id, "subtitles": True,
        "music_enabled": True, "music_mood": "upbeat",
    }
    await _run_stage(mode_a.stage_tts, payload)
    await _run_stage(mode_a.stage_animate, payload)
    await _run_stage(mode_a.stage_assemble, payload)

    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    assert project["status"] == "done"

    probe = _ffprobe_json(project["output_path"])
    audio_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    assert len(audio_streams) == 1

    project_dir = Path(project["output_path"]).parent
    credits = (project_dir / "credits.txt").read_text(encoding="utf-8")
    assert "upbeat-1.mp3" in credits
    assert "Background music" in credits
