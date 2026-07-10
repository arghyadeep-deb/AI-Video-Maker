"""Judgment gate #3 — Wan 2.2 TI2V-5B vs LTX-Video on the 5070 Ti.

Renders the SAME scene images + motion prompts through both backends,
times each, and writes a side-by-side folder for the owner's eyes.
The metric is quality-per-minute (specs/04-tasks/task-20a-gpu-worker.md);
the verdict goes in that task file and `scene_gen_backend` in config.toml.

Usage (inside the engines venv, torch cu128 installed):
    python scripts/bakeoff.py --images path/to/img1.jpg path/to/img2.jpg \
        --prompts "slow dolly-in, gentle parallax" "waves rolling, camera pans right"

This deliberately reuses SceneGenEngine itself (not a parallel code path),
so what the owner judges is exactly what production will run.
"""
import argparse
import json
import threading
import time
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker_agent.config import AgentConfig  # noqa: E402
from worker_agent.engines.scene_gen import SceneGenEngine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", nargs="+", required=True, type=Path)
    parser.add_argument("--prompts", nargs="+", required=True)
    parser.add_argument("--out", type=Path, default=Path("bakeoff-results"))
    parser.add_argument("--duration", type=float, default=5.0)
    args = parser.parse_args()
    if len(args.images) != len(args.prompts):
        parser.error("--images and --prompts must pair up 1:1")

    results = []
    for backend in ("wan", "ltx"):
        config = AgentConfig()
        config.scene_gen_backend = backend
        engine = SceneGenEngine(config)
        if not engine.probe():
            print(f"[{backend}] probe failed (deps/CUDA missing) - skipping")
            continue
        for i, (image, prompt) in enumerate(zip(args.images, args.prompts)):
            task_dir = args.out / backend / f"scene-{i}"
            task_dir.mkdir(parents=True, exist_ok=True)
            print(f"[{backend}] scene {i}: {prompt!r}")
            start = time.monotonic()
            clip = engine.run(
                task_dir, {"scene.jpg": image},
                {"prompt": prompt, "duration_s": args.duration},
                threading.Event(), lambda pct: None,
            )
            elapsed = time.monotonic() - start
            final = args.out / f"{backend}-scene-{i}.mp4"
            clip.replace(final)
            results.append({"backend": backend, "scene": i, "prompt": prompt,
                            "seconds": round(elapsed, 1), "file": final.name})
            print(f"[{backend}] scene {i}: {elapsed:.0f}s -> {final}")

    (args.out / "timings.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (args.out / "VERDICT.md").write_text(
        "# Bake-off verdict (judgment gate #3)\n\n"
        "Watch each wan-*.mp4 next to its ltx-*.mp4 (same image, same prompt).\n"
        "Timings are in timings.json. Judge **quality-per-minute**, then:\n\n"
        "1. Record the verdict + benchmarks in specs/04-tasks/task-20a-gpu-worker.md\n"
        "2. Set `scene_gen_backend` in worker-agent/config.toml\n",
        encoding="utf-8",
    )
    print(f"\nDone. Open {args.out}/ and judge; see VERDICT.md for what to record where.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
