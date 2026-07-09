"""TalkingHeadEngine interface — specs/02-research/03-talking-head-models.md,
specs/03-design/04-mode-a-pipeline.md.

Every engine (Wav2Lip CPU, SadTalker ZeroGPU, future colab-manual import)
implements this so the render_mode_a pipeline (task-12) never makes a raw
call to any of them directly.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TalkingHeadResult:
    video_path: str
    engine: str  # "wav2lip" | "sadtalker" | "colab-manual"


class TalkingHeadEngineError(Exception):
    pass


class TalkingHeadEngine(ABC):
    @abstractmethod
    async def render(self, portrait_path: str, wav_path: str, output_path: str) -> TalkingHeadResult:
        """Render a talking-head video of `portrait_path` speaking `wav_path`,
        writing an MP4 to `output_path`. Raises TalkingHeadEngineError on
        any failure (missing weights, subprocess crash, quota exhausted)."""
        raise NotImplementedError
