"""Generated-footage engine (~10-14 GB VRAM): one scene image + motion
prompt -> a real ~5 s AI video clip, via diffusers directly (no ComfyUI -
locked in specs/02-research/03-talking-head-models.md's platform verdicts).

Image->video (not text->video) is deliberate: the credited scene image
anchors content; the model adds camera+subject motion
(specs/01-requirements/05-mode-b-image-video.md).

Two backends, ONE ships enabled:
  * "wan" — Wan-AI/Wan2.2-TI2V-5B-Diffusers (Apache-2.0)
  * "ltx" — Lightricks/LTX-Video (openrail-style, commercial-ok tiers)

Judgment gate #3 (owner's eyes, quality-per-minute on the 5070 Ti):
run scripts/bakeoff.py, record the verdict in
specs/04-tasks/task-20a-gpu-worker.md, set `scene_gen_backend` accordingly.
Blackwell note (risk R12): both need torch CUDA 12.8+ builds (sm_120).
"""
import threading
from pathlib import Path
from typing import Callable

from worker_agent.config import AgentConfig
from worker_agent.engines.base import Engine, EngineAborted, EngineError

FPS = 24  # both models' native training rate; the VM's assembly re-times


class SceneGenEngine(Engine):
    name = "scene_gen"
    vram_required_mb = 10 * 1024

    def __init__(self, config: AgentConfig):
        self._backend = config.scene_gen_backend
        self._pipe = None

    def probe(self) -> bool:
        if self._backend not in ("wan", "ltx"):
            return False
        try:
            import diffusers  # noqa: F401
            import torch
        except ImportError:
            return False
        return torch.cuda.is_available()

    def _load(self):
        """Lazy, cached: model load is ~30-60 s and tens of GB of weights;
        it happens on first task, not at agent startup."""
        if self._pipe is not None:
            return self._pipe
        import torch

        if self._backend == "wan":
            from diffusers import WanImageToVideoPipeline

            self._pipe = WanImageToVideoPipeline.from_pretrained(
                "Wan-AI/Wan2.2-TI2V-5B-Diffusers", torch_dtype=torch.bfloat16
            )
        else:
            from diffusers import LTXImageToVideoPipeline

            self._pipe = LTXImageToVideoPipeline.from_pretrained(
                "Lightricks/LTX-Video", torch_dtype=torch.bfloat16
            )
        # 16 GB card + 10-14 GB model: offload keeps headroom for the VAE
        # decode spike instead of OOMing at the last step.
        self._pipe.enable_model_cpu_offload()
        return self._pipe

    def run(
        self,
        task_dir: Path,
        inputs: dict[str, Path],
        payload: dict,
        abort: threading.Event,
        progress: Callable[[float], None],
    ) -> Path:
        if abort.is_set():
            raise EngineAborted("scene_gen aborted before start")
        from diffusers.utils import export_to_video, load_image

        image_path = inputs.get("scene.jpg")
        if image_path is None:
            raise EngineError("scene_gen task has no scene.jpg input")
        prompt = payload.get("prompt", "")
        duration_s = float(payload.get("duration_s", 5.0))
        num_frames = max(9, int(duration_s * FPS) // 8 * 8 + 1)  # both models want 8k+1

        pipe = self._load()
        progress(10.0)
        if abort.is_set():
            raise EngineAborted("scene_gen aborted after model load")

        def _step_callback(pipeline, step, timestep, kwargs):
            if abort.is_set():
                # diffusers' supported interrupt mechanism: finishes the
                # current step then stops the denoise loop.
                pipeline._interrupt = True
            total = pipeline.num_timesteps or 1
            progress(10.0 + (step + 1) / total * 80.0)
            return kwargs

        image = load_image(str(image_path))
        result = pipe(
            image=image,
            prompt=prompt,
            num_frames=num_frames,
            callback_on_step_end=_step_callback,
        )
        if abort.is_set():
            raise EngineAborted("scene_gen aborted mid-denoise")

        out_path = task_dir / "clip.mp4"
        export_to_video(result.frames[0], str(out_path), fps=FPS)
        progress(100.0)
        return out_path
