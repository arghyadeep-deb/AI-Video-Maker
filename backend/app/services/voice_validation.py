"""Enrollment-sample validation — specs/01-requirements/11-personal-voice.md's
"Validation: 15-60 s of detected speech, one speaker, acceptable noise floor;
converted to mono 16 kHz" and specs/04-tasks/task-18-voice-cloning-voxcpm.md.

"Single speaker" has no real check here: a diarization model isn't part of
this project's free stack, and the enrollment flow only ever asks the
account owner to read alone in their own browser session. Faking a
speaker-count heuristic (e.g. off pitch-variance clustering) would be
unreliable and give false confidence, so this is an honest operational
assumption, not a machine-verified gate - matching this codebase's existing
principle of not faking verification it can't really do.
"""
from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

MIN_SPEECH_S = 15.0
MAX_SPEECH_S = 60.0
TARGET_SAMPLE_RATE = 16_000
# Below this, the recording is judged too noisy for a usable tone-color
# embedding - a rough but real signal-to-silence ratio, not a placeholder.
MIN_SNR_DB = 10.0
SILENCE_TOP_DB = 30  # librosa.effects.split's threshold below the clip's peak


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    speech_duration_s: float = 0.0
    snr_db: float = 0.0


def _speech_duration_s(y: np.ndarray, sr: int) -> float:
    intervals = librosa.effects.split(y, top_db=SILENCE_TOP_DB)
    return sum((end - start) for start, end in intervals) / sr


def _estimate_snr_db(y: np.ndarray, sr: int) -> float:
    """Ratio between loud (speech-dominant) and quiet (noise-floor-
    dominant) short-time frames. Deliberately NOT based on
    librosa.effects.split's silence/non-silence split: that only works if
    some frames are genuinely near-zero, which a recording with a
    noise floor present *throughout* (background hiss, hum, fan noise -
    the actual case this check needs to catch) never has - every frame
    would get classified as "loud enough", hiding the very thing being
    measured. Percentiles across framewise RMS energy are robust to that."""
    frame_rms = librosa.feature.rms(y=y)[0]
    if frame_rms.size == 0:
        return -np.inf

    noise_floor = max(np.percentile(frame_rms, 10), 1e-10)
    signal_level = np.percentile(frame_rms, 90)
    if signal_level <= 0:
        return -np.inf
    return 20 * np.log10(signal_level / noise_floor)


def validate_recording(path: Path) -> ValidationResult:
    """Loads the raw upload, mixes to mono, and validates it (WITHOUT
    resampling yet - resampling happens in normalize_for_enrollment, kept
    separate so validation numbers reflect the source recording)."""
    errors: list[str] = []
    y, sr = librosa.load(str(path), sr=None, mono=True)

    if y.size == 0:
        return ValidationResult(ok=False, errors=["Recording is empty"])

    speech_s = _speech_duration_s(y, sr)
    if speech_s < MIN_SPEECH_S:
        errors.append(f"Only {speech_s:.1f}s of speech detected - need at least {MIN_SPEECH_S:.0f}s")
    if speech_s > MAX_SPEECH_S:
        errors.append(f"{speech_s:.1f}s of speech detected - please keep it under {MAX_SPEECH_S:.0f}s")

    snr_db = _estimate_snr_db(y, sr)
    if snr_db < MIN_SNR_DB:
        errors.append("Background noise is too high - please record somewhere quieter")

    return ValidationResult(ok=not errors, errors=errors, speech_duration_s=speech_s, snr_db=snr_db)


def normalize_for_enrollment(src_path: Path, dest_path: Path) -> None:
    """Mono 16kHz WAV, ready for embedding extraction - the last step of
    "Validation: ... converted to mono 16 kHz" (task-18's own Files list)."""
    y, sr = librosa.load(str(src_path), sr=TARGET_SAMPLE_RATE, mono=True)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dest_path), y, TARGET_SAMPLE_RATE)


# specs/04-tasks/task-18-voice-cloning-voxcpm.md: "M/F prosody base
# auto-picked from enrollment sample pitch; user-overridable." A simple,
# real pitch-based heuristic (median voiced-frame f0 vs a fixed threshold
# near the typical male/female f0 boundary) - not a speaker-gender
# classifier, just a starting-point pick the user can always override.
PITCH_THRESHOLD_HZ = 165.0


def estimate_prosody_gender(path: Path) -> str:
    """Returns "female" or "male" - the auto-picked starting point for
    which stock edge-tts voice serves as this profile's conversion base."""
    y, sr = librosa.load(str(path), sr=None, mono=True)
    f0, voiced_flag, _voiced_prob = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr
    )
    voiced_f0 = f0[voiced_flag]
    if voiced_f0.size == 0:
        return "female"  # no confidently-voiced frames - arbitrary but harmless default, user-overridable
    median_f0 = float(np.median(voiced_f0))
    return "female" if median_f0 >= PITCH_THRESHOLD_HZ else "male"
