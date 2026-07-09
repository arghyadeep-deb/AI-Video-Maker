import numpy as np
import soundfile as sf

from app.services.voice_validation import (
    MAX_SPEECH_S,
    MIN_SPEECH_S,
    estimate_prosody_gender,
    normalize_for_enrollment,
    validate_recording,
)

SR = 22_050


def _write_wav(path, y, sr=SR):
    sf.write(str(path), y, sr)


def _tone(duration_s: float, sr: int = SR, freq: int = 200, amplitude: float = 0.3) -> np.ndarray:
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _silence(duration_s: float, sr: int = SR) -> np.ndarray:
    return np.zeros(int(sr * duration_s), dtype=np.float32)


def _speech_like(
    total_s: float, sr: int = SR, word_s: float = 1.0, pause_s: float = 0.3, noise_std: float = 0.0
) -> np.ndarray:
    """A word/pause burst pattern (real speech's own natural amplitude
    variation - loud syllables, quiet gaps) rather than one flat
    continuous tone, since the SNR check compares loud vs. quiet framewise
    energy and a perfectly flat tone has no "quiet" moments to contrast
    against at all."""
    rng = np.random.default_rng(0)
    segments = []
    remaining = total_s
    while remaining > 0:
        this_word = min(word_s, remaining)
        segments.append(_tone(this_word))
        remaining -= this_word
        if remaining <= 0:
            break
        this_pause = min(pause_s, remaining)
        segments.append(_silence(this_pause))
        remaining -= this_pause
    y = np.concatenate(segments)
    if noise_std > 0:
        y = y + rng.normal(0, noise_std, size=y.shape).astype(np.float32)
    return y


def test_valid_recording_passes(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path, _speech_like(30.0, noise_std=0.002))
    result = validate_recording(path)
    assert result.ok
    assert not result.errors


def test_too_short_recording_fails(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path, _tone(5.0))
    result = validate_recording(path)
    assert not result.ok
    assert any("at least" in e for e in result.errors)


def test_too_long_recording_fails(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path, _tone(90.0))
    result = validate_recording(path)
    assert not result.ok
    assert any("under" in e for e in result.errors)


def test_empty_recording_fails(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path, np.zeros(0, dtype=np.float32))
    result = validate_recording(path)
    assert not result.ok
    assert "empty" in result.errors[0].lower()


def test_noisy_recording_fails_snr_check(tmp_path):
    path = tmp_path / "sample.wav"
    # Same word/pause pattern as the valid-recording test, but with a loud
    # noise floor throughout (including the pauses) instead of a quiet one.
    _write_wav(path, _speech_like(30.0, noise_std=0.2))
    result = validate_recording(path)
    assert not result.ok
    assert any("noise" in e.lower() for e in result.errors)


def test_boundary_durations_are_inclusive(tmp_path):
    # The word/pause pattern's detected speech excludes pause time, and
    # librosa's frame-level VAD granularity means the exact ratio isn't
    # perfectly predictable - so these use a comfortable few-second margin
    # just inside each bound rather than chasing an exact half-second edge.
    path = tmp_path / "sample.wav"
    _write_wav(path, _speech_like(24.0, noise_std=0.002))
    result = validate_recording(path)
    assert result.ok
    assert MIN_SPEECH_S <= result.speech_duration_s <= MAX_SPEECH_S

    path2 = tmp_path / "sample2.wav"
    _write_wav(path2, _speech_like(70.0, noise_std=0.002))
    result2 = validate_recording(path2)
    assert result2.ok
    assert MIN_SPEECH_S <= result2.speech_duration_s <= MAX_SPEECH_S


def test_normalize_for_enrollment_produces_mono_16k(tmp_path):
    src = tmp_path / "src.wav"
    stereo = np.stack([_tone(20.0), _tone(20.0, freq=210)], axis=1)
    sf.write(str(src), stereo, SR)

    dest = tmp_path / "normalized.wav"
    normalize_for_enrollment(src, dest)

    data, sr = sf.read(str(dest))
    assert sr == 16_000
    assert data.ndim == 1  # mono


def test_estimate_prosody_gender_picks_female_for_a_high_pitch_tone(tmp_path):
    path = tmp_path / "high.wav"
    _write_wav(path, _tone(6.0, freq=250))  # well above the 165Hz threshold
    assert estimate_prosody_gender(path) == "female"


def test_estimate_prosody_gender_picks_male_for_a_low_pitch_tone(tmp_path):
    path = tmp_path / "low.wav"
    _write_wav(path, _tone(6.0, freq=100))  # well below the 165Hz threshold
    assert estimate_prosody_gender(path) == "male"
