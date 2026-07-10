"""VoxCPM HD voice on the local GPU (~8 GB VRAM) — the real-capacity home
for the HD-voice path task-18 built against a (still undeployed) HF Space,
and the Hindi-cloning fallback (risk R11) at full strength.

In-process (not subprocess): voxcpm is a normal pip package that coexists
with modern torch, unlike the 2023-era research repos.
"""
import threading
from pathlib import Path
from typing import Callable

from worker_agent.config import AgentConfig
from worker_agent.engines.base import Engine, EngineAborted, EngineError


class VoxCPMEngine(Engine):
    name = "voxcpm"
    vram_required_mb = 8 * 1024

    def __init__(self, config: AgentConfig):
        self._model = None

    def probe(self) -> bool:
        try:
            import torch  # noqa: F401
            import voxcpm  # noqa: F401
        except ImportError:
            return False
        import torch

        return torch.cuda.is_available()

    def _load(self):
        if self._model is None:
            from voxcpm import VoxCPM

            self._model = VoxCPM.from_pretrained("openbmb/VoxCPM-0.5B")
        return self._model

    def run(
        self,
        task_dir: Path,
        inputs: dict[str, Path],
        payload: dict,
        abort: threading.Event,
        progress: Callable[[float], None],
    ) -> Path:
        if abort.is_set():
            raise EngineAborted("voxcpm aborted before start")
        text = payload.get("text")
        if not text:
            raise EngineError("voxcpm task payload has no text")
        prompt_wav = inputs.get("reference.wav")  # cloning; absent = designed voice
        prompt_text = payload.get("reference_text")

        import soundfile as sf

        model = self._load()
        progress(20.0)
        if abort.is_set():
            raise EngineAborted("voxcpm aborted after model load")
        wav = model.generate(
            text=text,
            prompt_wav_path=str(prompt_wav) if prompt_wav else None,
            prompt_text=prompt_text,
        )
        out_path = task_dir / "speech.wav"
        sf.write(str(out_path), wav, 16000)
        progress(100.0)
        return out_path
