"""Local portrait styler — risk R2's wired fallback (specs/06-risks-and-future/01-risks.md):
"local styling on the owner's 5070 Ti (SD/SDXL+InstantID class...)". Needed
for real now that Gemini's image API free tier is gone (verified live
2026-07-11: 429, limit: 0) — the backend's honest raw-selfie fallback stays
as the last resort when this engine (or the whole worker) isn't available,
but when the owner's PC is online this produces an actual styled, identity-
preserving portrait.

Model decision (task-22, made once so this doesn't get re-litigated):
IP-Adapter FaceID (SDXL) over InstantID. Both need face-embedding
conditioning via insightface; IP-Adapter FaceID is diffusers-native
(`pipe.load_ip_adapter(...)`, a stable first-party API) where InstantID
needs a vendored community pipeline file — meaningfully more integration
risk for the same identity-preservation outcome, and the task file
pre-authorized this exact fallback if InstantID's dependencies "fight".
Lives in the agent's own modern venv (same as scene_gen) — insightface +
onnxruntime-gpu are ordinary, current packages, no 2023-era pins involved.
"""
import threading
from pathlib import Path
from typing import Callable

from worker_agent.config import AgentConfig
from worker_agent.engines.base import Engine, EngineAborted, EngineError

BASE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
IP_ADAPTER_REPO = "h94/IP-Adapter-FaceID"
IP_ADAPTER_WEIGHT = "ip-adapter-faceid_sdxl.bin"
FACE_ANALYSIS_MODEL = "buffalo_l"  # insightface's standard SDXL-scale face model pack

# specs/03-design/04-mode-a-pipeline.md's exact identity-pinning suffix -
# kept in sync with app/engines/image_styler.py's IDENTITY_SUFFIX so a
# styled portrait reads the same regardless of which engine produced it.
IDENTITY_SUFFIX = (
    ", same person, preserve facial identity, do not beautify or change age or gender, "
    "front-facing, neutral-to-mild expression, shoulders-up portrait, photorealistic"
)


class StylerEngine(Engine):
    name = "styler"
    vram_required_mb = 10 * 1024

    def __init__(self, config: AgentConfig):
        self._pipe = None
        self._face_app = None

    def probe(self) -> bool:
        try:
            import insightface  # noqa: F401
            import onnxruntime as ort
            import torch
            from diffusers import StableDiffusionXLPipeline  # noqa: F401
        except ImportError:
            return False
        if not torch.cuda.is_available():
            return False
        return "CUDAExecutionProvider" in ort.get_available_providers()

    def _load(self):
        """Lazy, cached - same rationale as scene_gen.py: model load is
        slow and large, happens on first task, not at agent startup."""
        if self._pipe is not None:
            return self._pipe, self._face_app
        import cv2
        import torch
        from diffusers import StableDiffusionXLPipeline
        from insightface.app import FaceAnalysis

        face_app = FaceAnalysis(
            name=FACE_ANALYSIS_MODEL, providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        face_app.prepare(ctx_id=0, det_size=(640, 640))

        pipe = StableDiffusionXLPipeline.from_pretrained(BASE_MODEL, torch_dtype=torch.bfloat16)
        pipe.load_ip_adapter(
            IP_ADAPTER_REPO, subfolder=None, weight_name=IP_ADAPTER_WEIGHT, image_encoder_folder=None
        )
        pipe.enable_model_cpu_offload()

        self._pipe, self._face_app = pipe, face_app
        self._cv2 = cv2
        return pipe, face_app

    def run(
        self,
        task_dir: Path,
        inputs: dict[str, Path],
        payload: dict,
        abort: threading.Event,
        progress: Callable[[float], None],
    ) -> Path:
        if abort.is_set():
            raise EngineAborted("styler aborted before start")

        selfie_path = inputs.get("selfie.jpg")
        if selfie_path is None:
            raise EngineError("styler task has no selfie.jpg input")
        persona_description = payload.get("prompt", "")
        width = int(payload.get("width", 1024))
        height = int(payload.get("height", 1024))

        pipe, face_app = self._load()
        progress(15.0)
        if abort.is_set():
            raise EngineAborted("styler aborted after model load")

        image_bgr = self._cv2.imread(str(selfie_path))
        if image_bgr is None:
            raise EngineError(f"could not read {selfie_path} as an image")
        faces = face_app.get(image_bgr)
        if not faces:
            # The backend's own face_check.py already gates uploads on a
            # detected face before this ever runs - reaching here with none
            # means a genuinely different detector disagreeing, not a user
            # error to blame them for.
            raise EngineError("no face detected in the selfie for identity conditioning")
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        face_embeds = face.normed_embedding

        def _step_callback(pipeline, step, timestep, kwargs):
            if abort.is_set():
                pipeline._interrupt = True
            total = pipeline.num_timesteps or 1
            progress(15.0 + (step + 1) / total * 80.0)
            return kwargs

        prompt = f"Restyle this person as: {persona_description}{IDENTITY_SUFFIX}"
        result = pipe(
            prompt=prompt,
            ip_adapter_image_embeds=[face_embeds],
            width=width,
            height=height,
            num_inference_steps=30,
            callback_on_step_end=_step_callback,
        )
        if abort.is_set():
            raise EngineAborted("styler aborted mid-denoise")

        out_path = task_dir / "portrait.png"
        result.images[0].save(out_path)
        progress(100.0)
        return out_path
