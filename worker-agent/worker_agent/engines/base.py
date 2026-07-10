"""Engine plugin interface. One engine = one `kind` of gpu_task."""
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable


class EngineError(Exception):
    pass


class EngineAborted(Exception):
    """Raised by an engine when the abort event fires mid-run (instant
    reclaim / lease lost). The agent discards output and reports nothing —
    the VM's lease-expiry path re-routes the job."""


class Engine(ABC):
    name: str
    vram_required_mb: int

    @abstractmethod
    def probe(self) -> bool:
        """True if this engine can actually run here (deps importable,
        weights/tools present). Must be cheap and must not touch the GPU."""

    @abstractmethod
    def run(
        self,
        task_dir: Path,
        inputs: dict[str, Path],
        payload: dict,
        abort: threading.Event,
        progress: Callable[[float], None],
    ) -> Path:
        """Run the task inside task_dir, return the result file path.
        Check `abort` at every practical point; raise EngineAborted when it
        fires. Raise EngineError on real failures."""
