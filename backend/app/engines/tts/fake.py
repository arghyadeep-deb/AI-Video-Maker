"""Deterministic TTSEngine stand-in for tests in other tasks (job worker,
Mode A/B assembly, subtitles) that need narration output without a network
call. Proves the engine-swap point from task-05's acceptance criteria.
"""
import json
from pathlib import Path

from app.engines.tts.base import SpeechResult, TTSEngine, WordTiming

MS_PER_WORD = 400  # arbitrary but deterministic - good enough for pipeline tests


class FakeTTSEngine(TTSEngine):
    async def speak(
        self, text: str, voice: str, out_path: Path, rate: str | None = None
    ) -> SpeechResult:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"FAKE_AUDIO")

        words = text.split()
        timings = [
            WordTiming(word=word, offset_ms=i * MS_PER_WORD, duration_ms=MS_PER_WORD - 50)
            for i, word in enumerate(words)
        ]

        # Same on-disk shape as EdgeTTSEngine, so downstream code reading
        # the sidecar file (not just the in-memory result) sees real data.
        timings_path = out_path.with_suffix(".timings.json")
        timings_path.write_text(
            json.dumps([t.__dict__ for t in timings], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return SpeechResult(audio_path=out_path, timings=timings)
