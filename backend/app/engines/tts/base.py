"""TTSEngine — specs/03-design/06-subtitle-timing.md.

Every narration call goes through this interface (edge-tts today; Supertonic
/ VoxCPM later per specs/01-requirements/07-free-stack-lock.md) so the
pipeline never depends on a specific engine's wire format.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WordTiming:
    word: str
    offset_ms: int
    duration_ms: int


@dataclass(frozen=True)
class SpeechResult:
    audio_path: Path
    timings: list[WordTiming]


class PersonalVoiceUnavailableError(Exception):
    """Base for any personal-voice tier's 'not available right now' error
    (Chatterbox Space down/quota, OpenVoice conversion failure, ...).
    Lives here - NOT in the engines' own modules - so tier-chaining code
    (pipelines/common.py) can catch it without importing torch-heavy
    engine modules it may not need. Task-23 voice upgrade."""


class TTSEngine(ABC):
    @abstractmethod
    async def speak(
        self, text: str, voice: str, out_path: Path, rate: str | None = None
    ) -> SpeechResult:
        """Synthesizes `text` in `voice`, writes audio to `out_path` and a
        `{out_path}.timings.json` sidecar, and returns both in-memory.
        """
