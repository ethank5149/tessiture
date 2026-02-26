import numpy as np
import pytest

from analysis.dsp.peak_detection import detect_harmonics
from analysis.dsp.preprocessing import preprocess_audio
from analysis.dsp.stft import compute_stft


def _sine_wave(freq_hz: float, sample_rate: int, duration_s: float, amplitude: float = 0.6) -> np.ndarray:
    t = np.arange(int(sample_rate * duration_s)) / float(sample_rate)
    return (amplitude * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)


def test_preprocess_audio_downmix_resample_and_normalize() -> None:
    sample_rate = 8000
    target_sr = 4000
    left = _sine_wave(440.0, sample_rate, 0.05)
    right = 0.5 * _sine_wave(440.0, sample_rate, 0.05)
    stereo_int16 = (np.vstack([left, right]) * 32767).astype(np.int16)

    result = preprocess_audio(
        stereo_int16,
        sample_rate=sample_rate,
        target_sr=target_sr,
        mono=True,
        normalize=True,
        peak=0.9,
    )

    expected_len = int(round(left.size * target_sr / sample_rate))
    assert result.sample_rate == target_sr, "Expected target sample rate in result."
    assert result.audio.ndim == 1, "Expected mono output after downmix."
    assert result.audio.dtype == np.float32, "Expected float32 output audio."
    assert result.audio.size == expected_len, "Expected resampled length to match target sample rate."
    assert result.info["resampled"] == 1.0, "Expected resampled flag set when sample rates differ."
    assert result.info["peak_after"] <= result.info["peak_before"] + 1e-6, "Expected normalization to not increase peak."


def test_compute_stft_shapes_and_peak_frequency() -> None:
    sample_rate = 8000
    audio = _sine_wave(440.0, sample_rate, 0.2)

    stft = compute_stft(audio, sample_rate=sample_rate, n_fft=256, hop_length=128)

    assert stft.spectrum.shape[0] == 129, "Expected n_fft/2 + 1 frequency bins."
    assert stft.spectrum.shape[1] == stft.times.size, "Expected spectrum time axis to match times length."
    assert stft.frequencies.size == 129, "Expected frequency grid length to match spectrum rows."
    assert stft.sigma_f.shape == stft.frequencies.shape, "Expected sigma_f to align with frequencies."

    peak_bin = int(np.argmax(np.mean(stft.spectrum, axis=1)))
    peak_freq = float(stft.frequencies[peak_bin])
    assert abs(peak_freq - 440.0) < 60.0, "Expected STFT peak near sine frequency."


def test_compute_stft_rejects_mismatched_window() -> None:
    audio = _sine_wave(220.0, 8000, 0.1)
    with pytest.raises(ValueError, match="window length"):
        compute_stft(audio, sample_rate=8000, n_fft=128, hop_length=64, window=np.ones(32))


def test_detect_harmonics_finds_candidates() -> None:
    frequencies = np.array([0, 100, 200, 300, 400, 500, 600, 700], dtype=np.float32)
    spectrum = np.array([[0.1], [0.2], [1.0], [0.2], [0.9], [0.2], [0.8], [0.1]], dtype=np.float32)

    frames = detect_harmonics(spectrum, frequencies, n_harmonics=3, freq_tolerance=5.0)

    assert len(frames) == 1, "Expected one harmonic frame for one time slice."
    assert frames[0].candidates, "Expected at least one harmonic candidate."
    candidate = frames[0].candidates[0]
    assert abs(candidate.f0 - 200.0) < 1e-3, "Expected fundamental near 200 Hz."
    assert len(candidate.harmonics) >= 3, "Expected harmonics matched for the candidate."


def test_detect_harmonics_returns_empty_for_silence() -> None:
    frequencies = np.array([0, 100, 200, 300], dtype=np.float32)
    spectrum = np.zeros((frequencies.size, 2), dtype=np.float32)

    frames = detect_harmonics(spectrum, frequencies)

    assert all(len(frame.candidates) == 0 for frame in frames), "Expected no candidates for silent spectrum."