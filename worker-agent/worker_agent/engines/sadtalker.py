"""SadTalker on the local GPU — the HD avatar engine while the PC is online
(specs/03-design/11-gpu-worker.md capabilities table, ~4 GB VRAM).

Subprocess wrapper around a local SadTalker checkout (2023-era research
code pins ancient deps — risk R12 — so it lives in its own venv,
`engines_python`, never in the agent's). setup.md documents the install;
setup_worker.ps1 automates it.
"""
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from worker_agent.config import AgentConfig
from worker_agent.engines.base import Engine, EngineAborted, EngineError

# Windows-only: without this, every subprocess launch flashes a fresh
# console window when the agent itself has no console to inherit from
# (headless via pythonw.exe) - see gpu.py's own copy of this same fix.
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class SadTalkerEngine(Engine):
    name = "sadtalker"
    vram_required_mb = 4 * 1024

    def __init__(self, config: AgentConfig):
        self._dir = config.sadtalker_dir
        self._python = config.engines_python

    def probe(self) -> bool:
        return (
            self._dir is not None
            and self._python is not None
            and (self._dir / "inference.py").exists()
            and (self._dir / "checkpoints").exists()
        )

    def run(
        self,
        task_dir: Path,
        inputs: dict[str, Path],
        payload: dict,
        abort: threading.Event,
        progress: Callable[[float], None],
    ) -> Path:
        portrait = next(p for name, p in inputs.items() if name.startswith("portrait"))
        audio = inputs["audio.wav"]
        result_dir = task_dir / "out"
        result_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self._python), str(self._dir / "inference.py"),
            "--driven_audio", str(audio),
            "--source_image", str(portrait),
            "--result_dir", str(result_dir),
            "--still", "--preprocess", "full",
        ]
        # inference.py's tqdm progress output easily exceeds the OS pipe
        # buffer; subprocess.PIPE with nothing draining it while polling
        # deadlocks the child on its next write() once that fills. A real
        # file has no such limit.
        log_path = task_dir / "sadtalker.log"
        with open(log_path, "w") as log_file:
            proc = subprocess.Popen(
                cmd, cwd=str(self._dir), stdout=log_file, stderr=subprocess.STDOUT, text=True,
                creationflags=_CREATE_NO_WINDOW,
            )
            # Poll-loop instead of wait(): abort (instant reclaim) must be
            # able to kill a long render within a second.
            while proc.poll() is None:
                if abort.is_set():
                    proc.kill()
                    proc.wait()
                    raise EngineAborted("sadtalker aborted")
                if abort.wait(1.0):
                    continue
        if proc.returncode != 0:
            tail = log_path.read_text(errors="replace")[-2000:]
            raise EngineError(f"sadtalker exited {proc.returncode}: {tail}")

        results = sorted(result_dir.rglob("*.mp4"))
        if not results:
            raise EngineError("sadtalker produced no mp4")
        progress(100.0)
        return results[-1]
