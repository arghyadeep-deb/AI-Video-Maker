"""edge-tts implementation of TTSEngine — specs/02-research/02-edge-tts.md.

edge-tts is an unofficial API; failures are wrapped so the pipeline gets an
honest, typed error rather than a raw websocket exception. WordBoundary
granularity must be requested explicitly (`boundary="WordBoundary"`) —
recent edge-tts versions default to SentenceBoundary, which would silently
break subtitle timing.
"""
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts

from app.engines.tts.base import SpeechResult, TTSEngine, WordTiming

# edge-tts offset/duration are in 100-nanosecond units (.NET TimeSpan ticks).
_TICKS_PER_MS = 10_000


class EdgeTTSUnavailableError(Exception):
    """edge-tts is unofficial and can go down; surfaced honestly to the UI."""


class EdgeTTSEngine(TTSEngine):
    def __init__(self, max_retries: int = 1):
        self._max_retries = max_retries

    async def speak(
        self, text: str, voice: str, out_path: Path, rate: str | None = None
    ) -> SpeechResult:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._speak_once(text, voice, out_path, rate)
            except Exception as exc:  # noqa: BLE001 - any transport failure retries once
                last_error = exc
                if attempt >= self._max_retries:
                    break
        raise EdgeTTSUnavailableError(
            "Could not reach the edge-tts service right now — it's an "
            "unofficial API and may be temporarily unreachable"
        ) from last_error

    async def _speak_once(
        self, text: str, voice: str, out_path: Path, rate: str | None
    ) -> SpeechResult:
        kwargs = {"rate": rate} if rate else {}
        communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary", **kwargs)

        timings: list[WordTiming] = []
        with out_path.open("wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    timings.append(
                        WordTiming(
                            word=chunk["text"],
                            offset_ms=chunk["offset"] // _TICKS_PER_MS,
                            duration_ms=chunk["duration"] // _TICKS_PER_MS,
                        )
                    )

        _write_timings_sidecar(out_path, timings)
        return SpeechResult(audio_path=out_path, timings=timings)


def _write_timings_sidecar(audio_path: Path, timings: list[WordTiming]) -> Path:
    # specs/03-design/08-data-model.md example: audio/scene-3.timings.json
    # (the audio extension is replaced, not appended to).
    timings_path = audio_path.with_suffix(".timings.json")
    timings_path.write_text(
        json.dumps([t.__dict__ for t in timings], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return timings_path


def to_wav16k(mp3_path: Path) -> Path:
    """16 kHz mono WAV — the format SadTalker/Wav2Lip expect (task-11)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    wav_path = mp3_path.with_suffix(".wav")
    subprocess.run(
        [ffmpeg, "-y", "-i", str(mp3_path), "-ar", "16000", "-ac", "1", str(wav_path)],
        check=True,
        capture_output=True,
    )
    return wav_path
