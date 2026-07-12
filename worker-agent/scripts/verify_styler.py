"""Isolated portrait-styler verification — task-22 Phase 2.

Runs StylerEngine directly against a real fixture selfie, no live agent,
no backend involvement. First run downloads SDXL base (~7 GB) + IP-Adapter
FaceID weights (~1.5 GB) from Hugging Face - one-time.

Usage (from worker-agent/, agent venv - has diffusers/insightface):
    .venv\\Scripts\\python.exe scripts\\verify_styler.py
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker_agent.config import AgentConfig  # noqa: E402
from worker_agent.engines.base import EngineAborted, EngineError  # noqa: E402
from worker_agent.engines.styler import StylerEngine  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SELFIE = REPO_ROOT / "backend" / "tests" / "fixtures" / "test_face.jpg"


def main() -> int:
    engine = StylerEngine(AgentConfig())
    print("probe():", engine.probe())
    if not engine.probe():
        print("FAIL: probe() false")
        return 1
    if not FIXTURE_SELFIE.exists():
        print(f"FAIL: fixture missing ({FIXTURE_SELFIE})")
        return 1

    task_dir = Path(tempfile.mkdtemp(prefix="styler-verify-"))
    inputs = {"selfie.jpg": FIXTURE_SELFIE}
    payload = {
        "prompt": "Astrologer, saffron robes, mystical study with celestial charts behind you",
        "width": 1024,
        "height": 1024,
    }
    try:
        start = time.monotonic()
        result = engine.run(
            task_dir, inputs, payload, threading.Event(), lambda pct: print(f"  progress: {pct:.0f}%")
        )
        elapsed = time.monotonic() - start
        final = REPO_ROOT / "worker-agent" / "bakeoff-results" / "styler-verify.png"
        final.parent.mkdir(parents=True, exist_ok=True)
        result.replace(final)
        print(f"OK: styled in {elapsed:.1f}s -> {final}")
        return 0
    except (EngineError, EngineAborted) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
