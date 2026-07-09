"""Wav2Lip local (CPU) engine — specs/02-research/03-talking-head-models.md.

Shells out to the vendored, pinned-commit Wav2Lip `inference.py` via
subprocess rather than importing it in-process: Wav2Lip's modules carry
global state (a cached mel-spectrogram basis, argparse-parsed globals) and
its script hardcodes relative paths (`temp/result.avi`) that only resolve
correctly when the process's cwd is the vendored repo itself - isolating
it as a subprocess sidesteps both problems cleanly.
"""
import asyncio
import sys
from pathlib import Path

from app.engines.talking_head.base import (
    TalkingHeadEngine,
    TalkingHeadEngineError,
    TalkingHeadResult,
)

VENDOR_DIR = Path(__file__).resolve().parents[3] / "vendor" / "wav2lip"
CHECKPOINT_PATH = VENDOR_DIR / "checkpoints" / "wav2lip_gan.pth"

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

        args = [
            self._python,
            "inference.py",
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
            cwd=str(VENDOR_DIR),
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
