"""Isolated SadTalker verification — task-22 Phase 1.

Runs SadTalkerEngine directly (no live agent, no config.toml `engines`
change, no backend involvement) against a real fixture portrait + audio,
and reports timing. This is the "direct engine run" step the task file
calls for before touching anything live.

Usage (from worker-agent/, using the AGENT venv - the engine wrapper just
shells out to the pins venv, it doesn't need torch itself):
    .venv\\Scripts\\python.exe scripts\\verify_sadtalker.py
"""
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker_agent.config import AgentConfig  # noqa: E402
from worker_agent.engines.base import EngineAborted, EngineError  # noqa: E402
from worker_agent.engines.sadtalker import SadTalkerEngine  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PORTRAIT = REPO_ROOT / "backend" / "tests" / "fixtures" / "test_face.jpg"
FIXTURE_AUDIO = REPO_ROOT / "backend" / "tests" / "fixtures" / "test_audio_16k.wav"


def main() -> int:
    config = AgentConfig()
    config.sadtalker_dir = Path(r"C:\tools\SadTalker")
    config.engines_python = Path(r"C:\tools\sadtalker-venv\Scripts\python.exe")

    engine = SadTalkerEngine(config)
    print("probe():", engine.probe())
    if not engine.probe():
        print("FAIL: probe() false - sadtalker_dir/engines_python/checkpoints not all present")
        return 1

    if not FIXTURE_PORTRAIT.exists() or not FIXTURE_AUDIO.exists():
        print(f"FAIL: fixtures missing ({FIXTURE_PORTRAIT.exists()=}, {FIXTURE_AUDIO.exists()=})")
        return 1

    task_dir = Path(tempfile.mkdtemp(prefix="sadtalker-verify-"))
    inputs = {"portrait.jpg": FIXTURE_PORTRAIT, "audio.wav": FIXTURE_AUDIO}
    try:
        start = time.monotonic()
        result = engine.run(
            task_dir, inputs, {}, threading.Event(), lambda pct: print(f"  progress: {pct:.0f}%")
        )
        elapsed = time.monotonic() - start
        final = REPO_ROOT / "worker-agent" / "bakeoff-results" / "sadtalker-verify.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(result, final)
        print(f"OK: rendered in {elapsed:.1f}s -> {final}")
        return 0
    except (EngineError, EngineAborted) as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        shutil.rmtree(task_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
