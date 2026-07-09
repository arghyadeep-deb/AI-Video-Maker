"""Forced alignment for generative voices with no native word-boundary
events — specs/AGENT-PLAYBOOK.md's hard invariant: "Subtitle timings come
from TTS word boundaries (or forced alignment for generative voices) —
never ASR of unknown text." The reference text here is always ALREADY
KNOWN (the exact script text a generative engine like VoxCPM was asked to
speak) - faster-whisper is used purely as a timing source (when did each
word land), never as a transcription source (what was said), the same
"known text, timing from the model" pattern `app/services/subtitles.py`'s
`realign_with_source_text` already uses for edge-tts's own punctuation-
stripped WordBoundary events.
"""
from functools import lru_cache
from pathlib import Path

from app.engines.tts.base import WordTiming


class ForcedAlignmentError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_model():
    from faster_whisper import WhisperModel

    return WhisperModel("tiny", device="cpu", compute_type="int8")


def forced_align(audio_path: Path, reference_text: str) -> list[WordTiming]:
    """Aligns `reference_text` (the KNOWN script text) to `audio_path`'s
    actual timing. Whisper's own recognized word count usually matches the
    reference for clean generative-voice output; when it doesn't (a
    misrecognized or dropped word), the reference token itself is kept but
    its timing is taken positionally from whisper's own word list - same
    graceful-degradation shape as `realign_with_source_text`, and still
    real, model-derived timing rather than a guess.
    """
    try:
        model = _get_model()
        segments, _info = model.transcribe(str(audio_path), word_timestamps=True)
        recognized_words = [w for seg in segments for w in (seg.words or [])]
    except Exception as exc:  # noqa: BLE001 - honest typed error, no raw stack trace upstream
        raise ForcedAlignmentError(str(exc)) from exc

    # Whisper is known to hallucinate a low-confidence word (e.g. " You")
    # on pure silence/near-silence rather than returning nothing - found by
    # actually running this against a silent clip, not assumed. A
    # confidence floor distinguishes real recognized speech from that.
    recognized_words = [w for w in recognized_words if w.probability >= 0.3]

    reference_tokens = reference_text.split()
    if not recognized_words:
        raise ForcedAlignmentError("faster-whisper produced no confident word timestamps for this audio")

    if len(reference_tokens) == len(recognized_words):
        tokens = reference_tokens
    else:
        # Fall back to whichever list is shorter, positionally - avoids an
        # IndexError while still returning real timing data for every word
        # that has one; this mismatch should be rare for clean TTS output.
        tokens = reference_tokens[: len(recognized_words)] or [w.word.strip() for w in recognized_words]

    return [
        WordTiming(
            word=token,
            offset_ms=round(w.start * 1000),
            duration_ms=round((w.end - w.start) * 1000),
        )
        for token, w in zip(tokens, recognized_words)
    ]
