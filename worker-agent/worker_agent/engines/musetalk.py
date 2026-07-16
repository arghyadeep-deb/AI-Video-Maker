"""MuseTalk lip-enhance pass (~6 GB VRAM) — same subprocess-in-own-venv
pattern as SadTalker; see specs/03-design/11-gpu-worker.md."""
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


class MuseTalkEngine(Engine):
    name = "musetalk"
    vram_required_mb = 6 * 1024

    def __init__(self, config: AgentConfig):
        self._dir = config.musetalk_dir
        self._python = config.engines_python

    def probe(self) -> bool:
        return (
            self._dir is not None
            and self._python is not None
            and (self._dir / "inference.py").exists()
        )

    def run(
        self,
        task_dir: Path,
        inputs: dict[str, Path],
        payload: dict,
        abort: threading.Event,
        progress: Callable[[float], None],
    ) -> Path:
        video = inputs["video.mp4"]
        audio = inputs["audio.wav"]
        out_path = task_dir / "enhanced.mp4"

        cmd = [
            str(self._python), str(self._dir / "inference.py"),
            "--video_path", str(video),
            "--audio_path", str(audio),
            "--result_path", str(out_path),
        ]
        proc = subprocess.Popen(
            cmd, cwd=str(self._dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=_CREATE_NO_WINDOW,
        )
        while proc.poll() is None:
            if abort.is_set():
                proc.kill()
                proc.wait()
                raise EngineAborted("musetalk aborted")
            abort.wait(1.0)
        if proc.returncode != 0:
            tail = (proc.stdout.read() if proc.stdout else "")[-2000:]
            raise EngineError(f"musetalk exited {proc.returncode}: {tail}")
        if not out_path.exists():
            raise EngineError("musetalk produced no output")
        progress(100.0)
        return out_path
