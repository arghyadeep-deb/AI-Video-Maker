"""Chatterbox Multilingual via Resemble AI's own public HF Space —
task-23's voice-expressiveness upgrade (the #1 "this is AI" tell).

Why this engine exists: the shipped default (edge-tts base speech ->
OpenVoice tone conversion) produces the user's *timbre* with edge-tts's
flat stock *prosody*. Chatterbox Multilingual (MIT, 500M) generates
speech end-to-end in the cloned voice - prosody, emotion and all - from
~10s of reference audio, which we already have: the user's enrollment
recording (`voice_profiles.sample_path`, consent-gated at enrollment).

Why Chatterbox and not IndicF5 (the research-preferred candidate, see
specs/02-research/07-voice-engine-alternatives.md): probed live
2026-07-18 - ai4bharat/IndicF5's public Space is in a runtime error
because the model repo itself became GATED (401 on config.json), so the
zero-hosting path for it is currently dead. ResembleAI's
Chatterbox-Multilingual-TTS Space is up and serves `/generate_tts_audio`
with `language_id` including "hi" (schema probed via /gradio_api/info,
not assumed). If/when the owner gets IndicF5 gated access, it can slot
in as another tier behind this same interface.

Same public-Space tradeoff as flux.py / ltx_public.py (their
infrastructure, genuinely free, could change without notice - the risk
class this project already accepts for edge-tts), and the same two
live-learned lessons applied from the LTX-2.3 upgrade: pass hf_token
(anonymous ZeroGPU buckets are tiny) and override gradio_client's ~21s
default httpx read-timeout.

Hard-invariant compliance: Chatterbox has no word-boundary events, so
subtitle timings come from forced alignment against the KNOWN script
text (app/services/forced_alignment.py) - never free ASR. Any failure
(Space down, quota, alignment) raises ChatterboxUnavailableError and the
narration chain degrades to OpenVoice -> stock, never silently.

The Space caps text at 300 chars/call: longer scene text is chunked at
sentence boundaries (Devanagari danda included) and the audio chunks are
concatenated. `rate` is accepted but unused - a generative model paces
itself; documented rather than faked.
"""
import asyncio
import re
from pathlib import Path
from typing import Callable, Optional

from gradio_client import Client, handle_file

from app.engines.tts.base import PersonalVoiceUnavailableError, SpeechResult, TTSEngine

PUBLIC_SPACE_ID = "ResembleAI/Chatterbox-Multilingual-TTS"
MAX_CHARS_PER_CALL = 300
# Neutral defaults straight from the Space's own schema; exaggeration 0.5
# is documented as "Neutral", higher gets unstable.
EXAGGERATION = 0.5
TEMPERATURE = 0.8
CFG_PACE = 0.5
DEFAULT_TIMEOUT_S = 90.0

_SENTENCE_SPLIT = re.compile(r"(?<=[।.!?])\s+")


class ChatterboxUnavailableError(PersonalVoiceUnavailableError):
    """Space unreachable, quota exhausted, malformed response, or
    forced alignment failed - callers degrade to the next voice tier."""


def chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CALL) -> list[str]:
    """Sentence-boundary chunking under the Space's 300-char cap. A single
    sentence longer than the cap is hard-split on whitespace (never
    mid-word; Devanagari codepoints must not be cut - AGENT-PLAYBOOK's
    conjunct warning)."""
    sentences = [s for s in _SENTENCE_SPLIT.split(text.strip()) if s]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        words = sentence.split()
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = word[:max_chars]  # pathological single "word" > cap
    if current:
        chunks.append(current)
    return chunks or [text[:max_chars]]


def language_id_for_voice(voice: str) -> str:
    """The pipelines pass edge-tts voice names ('hi-IN-SwaraNeural',
    'en-US-...') even to generative engines - reuse their language prefix
    rather than inventing a parallel language plumbing."""
    return "hi" if voice.lower().startswith("hi") else "en"


class ChatterboxRemoteEngine(TTSEngine):
    def __init__(
        self,
        reference_wav_path: Path,
        hf_token: Optional[str] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client_factory: Optional[Callable[[], Client]] = None,
    ):
        self._reference_wav_path = reference_wav_path
        self._timeout_s = timeout_s
        # httpx timeout override: gradio_client's own ~21s read-timeout
        # killed 100% of LTX-2.3 calls before ours ever applied (found
        # live, task-23) - same trap avoided here from day one.
        self._client_factory = client_factory or (
            lambda: Client(PUBLIC_SPACE_ID, token=hf_token, httpx_kwargs={"timeout": timeout_s + 15})
        )
        self._client: Optional[Client] = None

    def _get_client(self) -> Client:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def _call_once(self, chunk: str, language_id: str) -> str:
        client = self._get_client()
        result = client.predict(
            text_input=chunk,
            language_id=language_id,
            audio_prompt_path_input=handle_file(str(self._reference_wav_path)),
            exaggeration_input=EXAGGERATION,
            temperature_input=TEMPERATURE,
            seed_num_input=0,
            cfgw_input=CFG_PACE,
            api_name="/generate_tts_audio",
        )
        # Audio output: filepath str on current gradio, dict on older -
        # same defensive shape as ltx_public.py.
        if isinstance(result, dict):
            path = result.get("path") or result.get("url")
            if not path:
                raise ChatterboxUnavailableError(f"malformed audio response: {result!r}")
            return path
        return result

    def _synthesize_all(self, text: str, language_id: str, out_path: Path) -> None:
        chunks = chunk_text(text)
        result_paths = [Path(self._call_once(chunk, language_id)) for chunk in chunks]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if len(result_paths) == 1:
            out_path.write_bytes(result_paths[0].read_bytes())
            return
        # Multi-chunk: concatenate with soundfile (all chunks come from the
        # same model at the same sample rate; asserted, not assumed).
        import numpy as np
        import soundfile as sf

        arrays = []
        samplerate: Optional[int] = None
        for p in result_paths:
            data, sr = sf.read(str(p), always_2d=False)
            if samplerate is None:
                samplerate = sr
            elif sr != samplerate:
                raise ChatterboxUnavailableError(
                    f"chunk sample rates differ ({samplerate} vs {sr}) - refusing to concatenate"
                )
            arrays.append(data)
        sf.write(str(out_path), np.concatenate(arrays), samplerate, format="WAV")

    async def speak(
        self, text: str, voice: str, out_path: Path, rate: Optional[str] = None
    ) -> SpeechResult:
        if not self._reference_wav_path.exists():
            raise ChatterboxUnavailableError(
                f"enrollment sample not found at {self._reference_wav_path}"
            )
        language_id = language_id_for_voice(voice)
        n_chunks = len(chunk_text(text))
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._synthesize_all, text, language_id, out_path),
                timeout=self._timeout_s * n_chunks,
            )
        except ChatterboxUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - any Space/network failure degrades a tier
            raise ChatterboxUnavailableError(str(exc)) from exc

        # Timings: forced alignment against the KNOWN text (hard invariant -
        # never ASR of unknown text). Alignment failure degrades the whole
        # tier: better the flat-prosody OpenVoice voice with correct
        # subtitles than an expressive voice with wrong ones.
        from app.services.forced_alignment import ForcedAlignmentError, forced_align

        try:
            timings = forced_align(out_path, text)
        except ForcedAlignmentError as exc:
            raise ChatterboxUnavailableError(f"forced alignment failed: {exc}") from exc

        from app.engines.tts.edge import _write_timings_sidecar

        _write_timings_sidecar(out_path, timings)
        return SpeechResult(audio_path=out_path, timings=timings)
