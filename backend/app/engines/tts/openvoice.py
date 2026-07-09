"""Personal-voice TTS engine — specs/04-tasks/task-18-voice-cloning-voxcpm.md,
specs/01-requirements/11-personal-voice.md's two-stage pipeline: edge-tts
produces base speech + word timings (unchanged - the timings that drive
subtitles must survive conversion untouched), then OpenVoice's tone-color
converter (vendored at backend/vendor/openvoice/, pinned commit
74a1d147b17a8c3092dd5430504bd83ef6c7eb23, MIT license) converts only the
timbre to the enrolled user's own voice.

Only OpenVoice's converter is vendored/used here, not its own TTS
synthesis (`base_speakers/*.pth` were deliberately not downloaded) -
edge-tts is this project's base-speech generator per the spec above.
"""
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Optional

import torch

from app.engines.tts.base import SpeechResult, TTSEngine, WordTiming
from app.engines.tts.edge import EdgeTTSEngine, _write_timings_sidecar

VENDOR_DIR = Path(__file__).resolve().parents[3] / "vendor" / "openvoice"
CONFIG_PATH = VENDOR_DIR / "checkpoints_v2" / "converter" / "config.json"
CHECKPOINT_PATH = VENDOR_DIR / "checkpoints_v2" / "converter" / "checkpoint.pth"

if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))


class OpenVoiceUnavailableError(Exception):
    """Conversion failed (missing checkpoint, missing embedding, a bad
    reference sample, etc.) - callers must fall back to the stock voice
    with an explicit notice, per this project's hard invariant, never
    silently or with a stack trace."""


def is_available() -> bool:
    return CONFIG_PATH.exists() and CHECKPOINT_PATH.exists()


@lru_cache(maxsize=1)
def _get_converter():
    """Lazy singleton - the ~9.6s checkpoint load (benchmarked on this dev
    machine, CPU) happens once per process, not once per render."""
    if not is_available():
        raise OpenVoiceUnavailableError(
            f"OpenVoice checkpoint not found at {CHECKPOINT_PATH} - "
            "run backend/scripts/setup_models.py"
        )
    from openvoice.api import ToneColorConverter

    converter = ToneColorConverter(str(CONFIG_PATH), device="cpu")
    converter.load_ckpt(str(CHECKPOINT_PATH))
    return converter


def extract_embedding(audio_path: Path) -> torch.Tensor:
    """Extracts a tone-color embedding from a reference clip - used both
    at enrollment (the user's own validated, normalized sample) and,
    per-render, to get the base edge-tts voice's own "source" embedding
    for conversion."""
    try:
        converter = _get_converter()
        return converter.extract_se(str(audio_path))
    except Exception as exc:  # noqa: BLE001 - any OpenVoice failure -> honest typed error
        raise OpenVoiceUnavailableError(str(exc)) from exc


def save_embedding(embedding: torch.Tensor, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(embedding, dest_path)


def load_embedding(path: Path) -> torch.Tensor:
    if not path.exists():
        raise OpenVoiceUnavailableError(f"Voice embedding not found at {path}")
    return torch.load(path, map_location="cpu")


def _ffmpeg_bin() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise OpenVoiceUnavailableError("ffmpeg not found on PATH")
    return ffmpeg


class OpenVoiceConvertingEngine(TTSEngine):
    """Wraps a base TTSEngine (edge-tts by default) with an OpenVoice
    tone-color conversion pass to `target_embedding_path`. Word timings
    pass through from the base engine completely unchanged - conversion
    only ever changes timbre, never timing, per this project's "one audio
    clock" hard invariant.

    The conversion's own "source" embedding is extracted fresh from each
    call's own base-speech clip (the same edge-tts voice's own timbre,
    correct by construction) rather than pre-cached per voice id - a
    documented simplification (task-18's own scope): pre-extracting and
    disk-caching one embedding per stock voice id would save a small
    amount of redundant compute per scene, but adds a cache-invalidation
    surface for a ~0.8s-per-call cost this project's 1-2 user scale can
    easily afford.
    """

    def __init__(self, target_embedding_path: Path, base_engine: Optional[TTSEngine] = None):
        self._target_embedding_path = target_embedding_path
        self._base_engine = base_engine or EdgeTTSEngine()

    async def speak(
        self, text: str, voice: str, out_path: Path, rate: Optional[str] = None
    ) -> SpeechResult:
        base_path = out_path.with_name(f"{out_path.stem}.base{out_path.suffix}")
        base_result = await self._base_engine.speak(text, voice, base_path, rate)

        try:
            converter = _get_converter()
            src_se = extract_embedding(base_path)
            tgt_se = load_embedding(self._target_embedding_path)

            with tempfile.TemporaryDirectory() as tmp:
                # OpenVoice writes via soundfile, which only produces WAV/
                # FLAC/OGG - never MP3 - so the converted output lands as a
                # temp WAV first, then gets transcoded to out_path's own
                # extension (mp3, matching every other TTSEngine in this
                # project) via ffmpeg, already a hard dependency everywhere
                # else in this codebase.
                converted_wav = Path(tmp) / "converted.wav"
                converter.convert(str(base_path), src_se, tgt_se, output_path=str(converted_wav), tau=0.3)
                subprocess.run(
                    [_ffmpeg_bin(), "-y", "-i", str(converted_wav), str(out_path)],
                    check=True, capture_output=True, timeout=60,
                )
        except OpenVoiceUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - honest typed error, never a raw stack trace
            raise OpenVoiceUnavailableError(str(exc)) from exc
        finally:
            base_path.unlink(missing_ok=True)
            base_path.with_suffix(".timings.json").unlink(missing_ok=True)

        _write_timings_sidecar(out_path, base_result.timings)
        return SpeechResult(audio_path=out_path, timings=base_result.timings)
