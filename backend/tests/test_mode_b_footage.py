"""Generated-footage Mode B (task-20a): the footage stage's worker
round-trip and honest degradation, the clip-aware assembly filter, and
clip invalidation on image swap/re-source."""
import asyncio
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.db.connection import get_connection, run_migrations
from app.engines.ffmpeg.kenburns import SceneClip, build_kenburns_filter_complex
from app.jobs import gpu_router
from app.jobs.registry import JobContext
from app.pipelines import mode_b


# --- filter construction (no ffmpeg needed) ----------------------------------

def test_video_scene_uses_hold_tail_not_zoompan():
    clips = [
        SceneClip(index=0, image_path="a.jpg", duration_s=8.0, video_path="a.mp4"),
        SceneClip(index=1, image_path="b.jpg", duration_s=4.0),
    ]
    filter_complex, label = build_kenburns_filter_complex(clips, 1080, 1920)
    scene0, scene1 = filter_complex.split(";")[0], filter_complex.split(";")[1]
    # Scene 0 (clip): cover-fit + trim + last-frame hold, no Ken Burns.
    assert "tpad=stop_mode=clone" in scene0
    assert "force_original_aspect_ratio=increase" in scene0
    assert "zoompan" not in scene0
    # Scene 1 (photo): unchanged Ken Burns.
    assert "zoompan" in scene1
    assert "tpad" not in scene1
    assert label == "vout"


def test_hold_duration_matches_kenburns_timing_model():
    """The clip branch must pad to the exact same per-scene render duration
    the Ken Burns branch uses, or the xfade offsets (one-audio-clock) drift."""
    clips = [
        SceneClip(index=0, image_path="a.jpg", duration_s=8.0, video_path="a.mp4"),
        SceneClip(index=1, image_path="b.jpg", duration_s=4.0),
    ]
    filter_complex, _ = build_kenburns_filter_complex(clips, 1080, 1920, xfade_s=0.5)
    # First scene of 2: duration + xfade/2 = 8.25 - held then cut exactly.
    assert "trim=duration=8.250" in filter_complex
    assert "tpad=stop_mode=clone:stop=-1" in filter_complex


# --- stage_footage -----------------------------------------------------------

def _job_context(payload: dict, job_id: str = "job-1") -> JobContext:
    return JobContext(
        job_id=job_id, payload=payload,
        report=lambda pct: None, cancelled=lambda: False, register_process=lambda p: None,
    )


def _seed_project(conn, project_id: str, scenes: list[dict]) -> None:
    conn.execute("INSERT OR IGNORE INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')")
    conn.execute(
        "INSERT INTO projects (id, user_id, description, language, duration_s, format, status) "
        "VALUES (?, 'u1', 'd', 'en', 30, '9x16', 'accepted')",
        (project_id,),
    )
    conn.execute(
        "INSERT INTO script_versions (id, project_id, n, scenes_json, origin) "
        "VALUES (?, ?, 1, ?, 'generated')",
        (f"{project_id}-v1", project_id, json.dumps(scenes)),
    )
    conn.execute(
        "UPDATE projects SET accepted_version_id = ? WHERE id = ?",
        (f"{project_id}-v1", project_id),
    )
    conn.execute(
        "INSERT INTO jobs (id, user_id, project_id, type, status) "
        "VALUES ('job-1', 'u1', ?, 'render_mode_b', 'running')",
        (project_id,),
    )
    conn.commit()


SCENES = [
    {"id": 1, "text": "hello", "visual_hint": "sunrise over hills"},
    {"id": 2, "text": "world", "visual_hint": "city street at night"},
]


@pytest.fixture
def footage_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    # Instant lease expiry bookkeeping for the worker-lost test.
    monkeypatch.setenv("WORKER_TASK_MAX_ATTEMPTS", "1")
    get_settings.cache_clear()
    settings = get_settings()
    run_migrations(settings.db_path)
    conn = get_connection(settings.db_path)
    _seed_project(conn, "p1", SCENES)
    images_dir = settings.media_root / "users" / "u1" / "projects" / "p1" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for scene in SCENES:
        (images_dir / f"scene-{scene['id']}.jpg").write_bytes(b"jpg")
    yield conn, settings, images_dir
    conn.close()
    get_settings.cache_clear()


def _engine_notes(conn) -> str:
    return conn.execute("SELECT engine_notes FROM jobs WHERE id = 'job-1'").fetchone()[0]


def test_photo_level_is_a_noop_that_clears_stale_clips(footage_env):
    conn, settings, images_dir = footage_env
    stale = images_dir / "scene-1.mp4"
    stale.write_bytes(b"old clip")
    mode_b._upsert_media_asset(conn, "p1", "clip", 1, stale, {"engine": "scene_gen"})

    asyncio.run(mode_b.stage_footage(_job_context({"project_id": "p1", "visual_level": "photo"})))

    assert not stale.exists()
    row = conn.execute(
        "SELECT COUNT(*) FROM media_assets WHERE project_id = 'p1' AND kind = 'clip'"
    ).fetchone()
    assert row[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM gpu_tasks").fetchone()[0] == 0  # nothing submitted


def test_footage_with_no_worker_online_degrades_honestly(footage_env):
    conn, settings, images_dir = footage_env
    asyncio.run(
        mode_b.stage_footage(_job_context({"project_id": "p1", "visual_level": "footage"}))
    )
    assert "0/2 scenes generated" in _engine_notes(conn)
    assert "offline" in _engine_notes(conn)


def _fake_agent(db_path, settings, handler, cycles=50):
    """A fake worker thread speaking the router's own lease protocol:
    `handler(task_row, conn) -> bytes | Exception` per leased task."""

    def loop():
        for _ in range(cycles):
            conn = get_connection(db_path)
            try:
                gpu_router.record_worker_poll(conn, ["scene_gen"], 15000)
                row = gpu_router.lease_next_task(conn, ["scene_gen"], settings)
                if row is not None:
                    outcome = handler(row, conn)
                    if isinstance(outcome, Exception):
                        gpu_router.fail_task(conn, row["id"], str(outcome))
                    else:
                        out = settings.media_root / "gpu_tasks" / row["id"] / "clip.mp4"
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(outcome)
                        gpu_router.complete_task(conn, row["id"], out)
            finally:
                conn.close()
            threading.Event().wait(0.02)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def test_footage_generates_a_clip_per_scene(footage_env):
    conn, settings, images_dir = footage_env

    def handler(row, agent_conn):
        payload = json.loads(row["payload_json"])
        assert payload["duration_s"] == mode_b.FOOTAGE_CLIP_SECONDS
        assert payload["width"] == 1080 and payload["height"] == 1920
        assert payload["prompt"] in ("sunrise over hills", "city street at night")
        return f"clip-for-{payload['prompt']}".encode()

    _fake_agent(settings.db_path, settings, handler)
    asyncio.run(
        mode_b.stage_footage(_job_context({"project_id": "p1", "visual_level": "footage"}))
    )

    assert (images_dir / "scene-1.mp4").read_bytes() == b"clip-for-sunrise over hills"
    assert (images_dir / "scene-2.mp4").read_bytes() == b"clip-for-city street at night"
    rows = conn.execute(
        "SELECT scene_id FROM media_assets WHERE project_id = 'p1' AND kind = 'clip' ORDER BY scene_id"
    ).fetchall()
    assert [r["scene_id"] for r in rows] == [1, 2]
    assert _engine_notes(conn) == "footage: 2/2 scenes generated"


def test_worker_lost_mid_render_keeps_partial_clips_and_says_so(footage_env):
    conn, settings, images_dir = footage_env
    seen = {"n": 0}

    def handler(row, agent_conn):
        seen["n"] += 1
        if seen["n"] == 1:
            return b"first clip"
        return RuntimeError("CUDA OOM")  # second scene dies on the PC

    _fake_agent(settings.db_path, settings, handler)
    asyncio.run(
        mode_b.stage_footage(_job_context({"project_id": "p1", "visual_level": "footage"}))
    )

    assert (images_dir / "scene-1.mp4").exists()
    assert not (images_dir / "scene-2.mp4").exists()
    notes = _engine_notes(conn)
    assert "1/2 scenes generated" in notes and "photo motion" in notes


def test_delete_scene_clip_removes_row_and_file(footage_env):
    conn, settings, images_dir = footage_env
    clip = images_dir / "scene-1.mp4"
    clip.write_bytes(b"clip")
    mode_b._upsert_media_asset(conn, "p1", "clip", 1, clip, {"engine": "scene_gen"})

    mode_b.delete_scene_clip(conn, "p1", 1)
    assert not clip.exists()
    assert conn.execute(
        "SELECT COUNT(*) FROM media_assets WHERE project_id = 'p1' AND kind = 'clip'"
    ).fetchone()[0] == 0
    mode_b.delete_scene_clip(conn, "p1", 1)  # idempotent


# --- real assembly of a mixed clip/photo video -------------------------------

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_mixed_clip_and_photo_scenes_assemble_with_real_ffmpeg(tmp_path):
    """A real ffmpeg render mirroring the assemble stage exactly: one
    AI-clip scene + one Ken Burns scene, per-scene audio concat, `-shortest`
    (production's one-audio-clock mechanism), xfaded, correct total length."""
    from app.engines.ffmpeg.builder import (
        FFmpegCommand,
        input_audio,
        input_image_still,
        input_video,
    )
    from app.engines.ffmpeg.kenburns import build_audio_concat_filter

    clip_path = tmp_path / "scene1.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=2",
         str(clip_path)],
        check=True, capture_output=True, timeout=30,
    )
    image_path = tmp_path / "scene2.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x2a5298:s=1080x1920", "-frames:v", "1",
         str(image_path)],
        check=True, capture_output=True, timeout=30,
    )
    audio_paths = []
    for i, seconds in enumerate((3.0, 2.0)):
        audio = tmp_path / f"audio-{i}.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=24000",
             "-af", "volume=0.01", "-t", f"{seconds:.3f}", "-q:a", "9", str(audio)],
            check=True, capture_output=True, timeout=30,
        )
        audio_paths.append(audio)

    # Scene 0: 3 s of audio but only a 2 s clip -> the hold tail must bridge.
    clips = [
        SceneClip(index=0, image_path=str(image_path), duration_s=3.0, video_path=str(clip_path)),
        SceneClip(index=1, image_path=str(image_path), duration_s=2.0),
    ]
    video_filter, video_label = build_kenburns_filter_complex(clips, 540, 960)
    audio_filter, audio_label = build_audio_concat_filter(2, audio_input_start_index=2)
    inputs = [
        input_video(clip_path),
        input_image_still(image_path),
        input_audio(audio_paths[0]),
        input_audio(audio_paths[1]),
    ]
    out = tmp_path / "out.mp4"
    command = FFmpegCommand(
        inputs=inputs,
        filter_complex=f"{video_filter};{audio_filter}",
        maps=["-map", f"[{video_label}]", "-map", f"[{audio_label}]"],
        output_args=["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"],
        output_path=str(out),
    )
    subprocess.run(command.to_args("ffmpeg"), check=True, capture_output=True, timeout=120)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    duration = float(probe.stdout.strip())
    # One-audio-clock: total length == sum of scene audio durations.
    assert duration == pytest.approx(5.0, abs=0.35)

    # Regression guard (found live 2026-07-16): `-shortest` on the final mux
    # does not reliably truncate a filter_complex-generated video stream, so
    # a zoompan frame-count bug (feeding it a *looped* image input instead
    # of a single frame made it multiply its own `d` output frames per
    # input frame it received) produced a real ~91,000-frame, 3035 s video
    # for what should have been ~55 s - checking the container's overall
    # `format=duration` alone would NOT have caught this. Assert the video
    # stream's own duration directly, independent of the audio stream.
    video_probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    video_duration = float(video_probe.stdout.strip())
    assert video_duration == pytest.approx(5.0, abs=0.35)
