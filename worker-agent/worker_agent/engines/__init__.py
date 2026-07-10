"""Engine plugin registry — specs/03-design/11-gpu-worker.md capabilities
table. The agent probes each configured engine at startup and advertises
only what actually loads ("VRAM-probed enablement"); the VM routes
accordingly, so a capability in a poll is a real promise.
"""
from worker_agent.config import AgentConfig
from worker_agent.engines.base import Engine
from worker_agent.gpu import GpuStatus


def _all_engines(config: AgentConfig) -> dict[str, Engine]:
    # Imports are local so a missing heavy dependency (torch, diffusers)
    # fails that one engine's probe instead of crashing the whole agent.
    from worker_agent.engines.musetalk import MuseTalkEngine
    from worker_agent.engines.sadtalker import SadTalkerEngine
    from worker_agent.engines.scene_gen import SceneGenEngine
    from worker_agent.engines.voxcpm import VoxCPMEngine

    return {
        "sadtalker": SadTalkerEngine(config),
        "voxcpm": VoxCPMEngine(config),
        "musetalk": MuseTalkEngine(config),
        "scene_gen": SceneGenEngine(config),
    }


def discover(config: AgentConfig, gpu: GpuStatus) -> dict[str, Engine]:
    """The engines this agent can honestly advertise right now: enabled in
    config, probe passed (deps + weights importable/present), and the card
    physically has enough total VRAM."""
    available: dict[str, Engine] = {}
    total_vram_mb = gpu.vram_free_mb  # probed at startup, before any lease
    for name, engine in _all_engines(config).items():
        if name not in config.engines:
            continue
        if engine.vram_required_mb > total_vram_mb:
            continue
        try:
            if engine.probe():
                available[name] = engine
        except Exception:  # noqa: BLE001 - a broken probe = not available
            continue
    return available
