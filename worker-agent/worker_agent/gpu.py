"""GPU status probe via nvidia-smi — the auto-yield signal.

Checked between jobs, before every lease (specs/03-design/11-gpu-worker.md:
"the owner's work is never contended mid-session"). The runner is
injectable so tests exercise the parsing and yield decisions without a GPU.
"""
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional

QUERY_CMD = [
    "nvidia-smi",
    "--query-gpu=utilization.gpu,memory.free,name",
    "--format=csv,noheader,nounits",
]

# Windows-only: nvidia-smi is a console app, and without this flag every
# invocation flashes a brand new console window on screen - invisible when
# the agent itself runs in a terminal (the child just inherits it), but a
# real, repeating (every idle_check_interval_s, by default 15s) visual
# glitch once the agent runs headless via pythonw.exe with no console of
# its own to inherit - found live 2026-07-16 right after setting the
# worker up to run silently at logon.
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


@dataclass(frozen=True)
class GpuStatus:
    util_pct: float
    vram_free_mb: int
    name: str


def _default_runner(cmd: list[str]) -> str:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=10, check=True,
        creationflags=_CREATE_NO_WINDOW,
    ).stdout


def probe(runner: Callable[[list[str]], str] = _default_runner) -> Optional[GpuStatus]:
    """None means "no usable NVIDIA GPU visible" — the agent then idles
    (it never advertises capabilities it can't serve)."""
    try:
        output = runner(QUERY_CMD)
    except (OSError, subprocess.SubprocessError):
        return None
    line = output.strip().splitlines()
    if not line:
        return None
    parts = [p.strip() for p in line[0].split(",")]
    if len(parts) < 3:
        return None
    try:
        return GpuStatus(util_pct=float(parts[0]), vram_free_mb=int(float(parts[1])), name=parts[2])
    except ValueError:
        return None


def owner_is_using_gpu(status: GpuStatus, max_util_pct: float, min_vram_free_mb: int) -> bool:
    """True = yield: another process (game, training run, editing app) has
    the card. Either signal alone is enough — a paused training run can sit
    at 0% util while still holding VRAM."""
    return status.util_pct > max_util_pct or status.vram_free_mb < min_vram_free_mb
