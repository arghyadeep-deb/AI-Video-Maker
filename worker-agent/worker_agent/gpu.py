"""GPU status probe via nvidia-smi — the auto-yield signal.

Checked between jobs, before every lease (specs/03-design/11-gpu-worker.md:
"the owner's work is never contended mid-session"). The runner is
injectable so tests exercise the parsing and yield decisions without a GPU.
"""
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

QUERY_CMD = [
    "nvidia-smi",
    "--query-gpu=utilization.gpu,memory.free,name",
    "--format=csv,noheader,nounits",
]


@dataclass(frozen=True)
class GpuStatus:
    util_pct: float
    vram_free_mb: int
    name: str


def _default_runner(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True).stdout


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
