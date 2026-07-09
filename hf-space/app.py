"""Gradio ZeroGPU Space wrapping SadTalker — specs/03-design/04-mode-a-pipeline.md.

Deploy target: a Hugging Face Space (Gradio SDK, ZeroGPU hardware). This
file is written here but NOT executed in this repo/session — it only runs
once deployed to Hugging Face's own infrastructure, driven by this
directory's requirements.txt and the vendored SadTalker checkout (see
SETUP.md — the owner does that step, since it involves downloading and
running a third-party research repo's pretrained weights, same class of
action as the Wav2Lip vendoring in backend/vendor/).

Contract (called by backend/app/engines/talking_head/sadtalker_zerogpu.py
via gradio_client, api_name="/render"): render(portrait, wav) -> path to an MP4.
"""
import subprocess
import tempfile
from pathlib import Path

import gradio as gr
import spaces

SADTALKER_DIR = Path(__file__).parent / "SadTalker"
CHECKPOINT_DIR = SADTALKER_DIR / "checkpoints"


@spaces.GPU(duration=120)
def render(portrait: str, wav: str) -> str:
    """portrait: path to a 1024x1024 front-facing photo.
    wav: path to a 16kHz WAV file.
    Returns: path to the rendered MP4.
    """
    with tempfile.TemporaryDirectory() as result_dir:
        subprocess.run(
            [
                "python", str(SADTALKER_DIR / "inference.py"),
                "--driven_audio", wav,
                "--source_image", portrait,
                "--result_dir", result_dir,
                "--still",
                "--preprocess", "full",
                "--checkpoint_dir", str(CHECKPOINT_DIR),
            ],
            check=True,
            cwd=str(SADTALKER_DIR),
        )
        rendered = sorted(Path(result_dir).glob("*.mp4"))
        if not rendered:
            raise RuntimeError("SadTalker produced no output video")
        # Copy out before the tempdir is cleaned up - Gradio needs the file
        # to still exist after this function returns.
        output_path = Path(tempfile.mkdtemp()) / "result.mp4"
        output_path.write_bytes(rendered[0].read_bytes())
        return str(output_path)


demo = gr.Interface(
    fn=render,
    inputs=[
        gr.File(label="Portrait (1024x1024, front-facing)", type="filepath"),
        gr.File(label="Audio (16kHz WAV)", type="filepath"),
    ],
    outputs=gr.File(label="Rendered MP4"),
)

if __name__ == "__main__":
    demo.launch()
