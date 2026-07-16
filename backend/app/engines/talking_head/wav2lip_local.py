"""Wav2Lip local (CPU) engine — specs/02-research/03-talking-head-models.md.

Shells out to the vendored, pinned-commit Wav2Lip `inference.py` via
subprocess rather than importing it in-process: Wav2Lip's modules carry
global state (a cached mel-spectrogram basis, argparse-parsed globals) and
its script hardcodes relative paths (`temp/result.avi`) that only resolve
correctly when the process's cwd is the vendored repo itself - isolating
it as a subprocess sidesteps both problems cleanly.

Each invocation runs in its own isolated temp directory (not VENDOR_DIR
itself) so concurrent/overlapping Wav2Lip processes can never write to the
same `temp/result.avi` path - a real bug found live 2026-07-16: two
invocations sharing that fixed relative path raced, and the final video
silently ended up ~1.8x longer than its own audio (mismatched frame count
from the other run) with no error at all - the render *looked* successful.
Invoking inference.py by its absolute path (not a bare relative name)
keeps Python's own sibling-module imports (`from models import Wav2Lip`,
etc.) working correctly even with a different cwd, since sys.path[0] is
derived from the script's own path, not the process's cwd.
"""
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from app.engines.talking_head.base import (
    TalkingHeadEngine,
    TalkingHeadEngineError,
    TalkingHeadResult,
)

VENDOR_DIR = Path(__file__).resolve().parents[3] / "vendor" / "wav2lip"
CHECKPOINT_PATH = VENDOR_DIR / "checkpoints" / "wav2lip_gan.pth"
INFERENCE_SCRIPT = VENDOR_DIR / "inference.py"

STDOUT_TAIL_CHARS = 2000


class Wav2LipLocalEngine(TalkingHeadEngine):
    def __init__(self, python_executable: str | None = None):
        self._python = python_executable or sys.executable

    async def render(self, portrait_path: str, wav_path: str, output_path: str) -> TalkingHeadResult:
        if not CHECKPOINT_PATH.exists():
            raise TalkingHeadEngineError(
                f"Wav2Lip checkpoint not found at {CHECKPOINT_PATH} - run scripts/setup_models.py"
            )

        output_abs = str(Path(output_path).resolve())
        Path(output_abs).parent.mkdir(parents=True, exist_ok=True)

        run_dir = Path(tempfile.mkdtemp(prefix="wav2lip_run_"))
        (run_dir / "temp").mkdir()
        try:
            args = [
                self._python,
                str(INFERENCE_SCRIPT),
                "--checkpoint_path",
                str(CHECKPOINT_PATH),
                "--face",
                str(Path(portrait_path).resolve()),
                "--audio",
                str(Path(wav_path).resolve()),
                "--outfile",
                output_abs,
            ]
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(run_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()

            if proc.returncode != 0:
                tail = stdout.decode(errors="replace")[-STDOUT_TAIL_CHARS:]
                raise TalkingHeadEngineError(f"Wav2Lip inference failed (exit {proc.returncode}):\n{tail}")

            if not Path(output_abs).exists():
                tail = stdout.decode(errors="replace")[-STDOUT_TAIL_CHARS:]
                raise TalkingHeadEngineError(
                    f"Wav2Lip inference exited cleanly but produced no output file:\n{tail}"
                )

            return TalkingHeadResult(video_path=output_abs, engine="wav2lip")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
