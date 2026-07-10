"""Agent configuration — a small TOML file, not env vars, because the agent
is an installed desktop service the owner edits by hand (see setup.md).

Locked defaults from specs/03-design/11-gpu-worker.md "The owner's GPU
comes first": don't lease when another process pushes utilization past 20%
or free VRAM under 10 GB; schedule windows keep the agent idle outside
allowed hours at zero GPU cost.
"""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentConfig:
    vm_url: str = ""
    token: str = ""
    # Long-poll + heartbeat cadence (design doc: 25 s cycles, 10 s beats).
    poll_wait_s: float = 20.0
    heartbeat_interval_s: float = 10.0
    idle_check_interval_s: float = 15.0
    # Owner-first yield thresholds.
    max_gpu_util_pct: float = 20.0
    min_vram_free_mb: int = 10 * 1024
    # Active windows, e.g. ["22:00-08:00"]; empty list = always active.
    active_hours: list[str] = field(default_factory=list)
    # Upload pacing in Mbit/s; 0 = unlimited.
    bandwidth_limit_mbps: float = 0.0
    # Scratch space for in-flight task files; wiped per task.
    work_dir: Path = Path.home() / ".aivideomaker-worker"
    # Engine enablement. Only engines listed here are even probed; the
    # probe (deps + weights + VRAM fit) then decides what's advertised.
    engines: list[str] = field(default_factory=lambda: ["sadtalker", "scene_gen"])
    # scene_gen backend: "wan" (Wan 2.2 TI2V-5B) or "ltx" (LTX-Video).
    # Provisional default; judgment gate #3 (scripts/bakeoff.py, owner's
    # eyes, quality-per-minute on the 5070 Ti) picks the real one - record
    # the verdict in specs/04-tasks/task-20a-gpu-worker.md.
    scene_gen_backend: str = "wan"
    # External tool locations for the subprocess-wrapped engines.
    sadtalker_dir: Path | None = None
    musetalk_dir: Path | None = None
    engines_python: Path | None = None  # venv python with torch cu128 etc.


def load_config(path: Path) -> AgentConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = AgentConfig()
    for key, value in data.items():
        if not hasattr(cfg, key):
            raise ValueError(f"Unknown config key: {key}")
        current = getattr(cfg, key)
        if isinstance(current, Path) or key in ("sadtalker_dir", "musetalk_dir", "engines_python"):
            value = Path(value)
        setattr(cfg, key, value)
    if not cfg.vm_url or not cfg.token:
        raise ValueError("config must set vm_url and token")
    cfg.vm_url = cfg.vm_url.rstrip("/")
    return cfg
