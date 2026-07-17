"""Gradio ZeroGPU Space: FLUX.1-schnell (image) -> LTX-Video (animate) —
task-23-quality-and-ops.md's Generated Footage reliability fix.

Deploy target: a Hugging Face Space (Gradio SDK, ZeroGPU hardware). This
file only runs once deployed to Hugging Face's own infrastructure - not
executed in this repo/session. Mirrors hf-space/app.py's own pattern
(SadTalker ZeroGPU Space): the owner's own deployed Space, called via
gradio_client, never a third-party demo.

Replaces the home GPU worker's scene_gen engine as the primary tier for
Mode B's "Generated footage" visual level - the local 12GB laptop card
needed enable_model_cpu_offload() to fit Wan2.2 at all, which made even
model loading alone take 30+ minutes (specs/04-tasks/task-23-quality-and-ops.md's
own live finding). ZeroGPU's H200 (~70GB VRAM) needs no such offload;
spike-tested live at 16.6s total for a real LTX-Video image-to-video call,
comfortably inside ZeroGPU's 120s per-call ceiling.

Two models chosen deliberately, both permissively licensed (Apache-2.0):
- FLUX.1-schnell: generates a scene-matched image directly from the
  scene's own text (replacing stock-photo keyword search entirely - the
  root cause of task-23's "image doesn't match the words" complaint).
  ~0.9s/image in 1-4 steps.
- LTX-Video: animates that generated image into a short real motion clip
  (not a Ken Burns pan/zoom of a static image).

Contract (called by a new backend/app/engines/scene_gen/zerogpu.py via
gradio_client, api_name="/generate"):
generate(prompt, duration_s, width, height) -> path to an MP4.
"""
import tempfile
from pathlib import Path

import gradio as gr
import spaces
import torch

FLUX_MODEL = "black-forest-labs/FLUX.1-schnell"
LTX_MODEL = "Lightricks/LTX-Video"
FPS = 24  # LTX-Video's native training rate

_flux_pipe = None
_ltx_pipe = None


def _get_flux_pipe():
    global _flux_pipe
    if _flux_pipe is None:
        from diffusers import FluxPipeline

        _flux_pipe = FluxPipeline.from_pretrained(FLUX_MODEL, torch_dtype=torch.bfloat16)
        _flux_pipe.enable_model_cpu_offload()
    return _flux_pipe


def _get_ltx_pipe():
    global _ltx_pipe
    if _ltx_pipe is None:
        from diffusers import LTXImageToVideoPipeline

        _ltx_pipe = LTXImageToVideoPipeline.from_pretrained(LTX_MODEL, torch_dtype=torch.bfloat16)
        _ltx_pipe.enable_model_cpu_offload()
    return _ltx_pipe


# STYLE_SUFFIX keeps every scene in one video visually cohesive rather than
# each generated image looking like it came from a different artist/style -
# same rationale as the avatar pipeline's own IDENTITY_SUFFIX pattern
# (specs/03-design/04-mode-a-pipeline.md), just for style consistency
# instead of facial identity.
STYLE_SUFFIX = ", cinematic lighting, photorealistic, consistent color grade, high detail"


@spaces.GPU(duration=60)
def generate(prompt: str, duration_s: float = 5.0, width: int = 1080, height: int = 1920) -> str:
    """prompt: the scene's own visual description (not just a 2-4 word hint).
    duration_s: target clip length in seconds (short - a few seconds).
    width/height: output resolution (project format, e.g. 1080x1920 for 9x16).
    Returns: path to the rendered MP4.
    """
    flux = _get_flux_pipe()
    # FLUX.1-schnell wants a distinct resolution multiple of 16; downscale
    # for the generation pass, LTX will resample to the exact target itself.
    gen_width = (width // 16) * 16
    gen_height = (height // 16) * 16
    image = flux(
        prompt=f"{prompt}{STYLE_SUFFIX}",
        width=min(gen_width, 1024),
        height=min(gen_height, 1024),
        num_inference_steps=4,
        guidance_scale=0.0,
    ).images[0]

    ltx = _get_ltx_pipe()
    num_frames = max(9, int(duration_s * FPS) // 8 * 8 + 1)  # LTX wants 8k+1 frames
    video_frames = ltx(
        image=image,
        prompt=prompt,
        width=gen_width,
        height=gen_height,
        num_frames=num_frames,
    ).frames[0]

    from diffusers.utils import export_to_video

    output_path = Path(tempfile.mkdtemp()) / "clip.mp4"
    export_to_video(video_frames, str(output_path), fps=FPS)
    return str(output_path)


demo = gr.Interface(
    fn=generate,
    inputs=[
        gr.Textbox(label="Scene description"),
        gr.Number(label="Duration (seconds)", value=5.0),
        gr.Number(label="Width", value=1080),
        gr.Number(label="Height", value=1920),
    ],
    outputs=gr.File(label="Rendered MP4"),
)

if __name__ == "__main__":
    demo.launch()
