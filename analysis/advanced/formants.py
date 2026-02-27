"""Formant estimation utilities (F1/F2/F3 trajectories)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from analysis.dsp.peak_detection import _find_peaks
from analysis.dsp.preprocessing import preprocess_audio
from analysis.dsp.stft import compute_stft


@dataclass(frozen=True)
class FormantFrame:
    """Single-frame formant estimates with quality metrics."""

    time_s: float
    f1_hz: float
    f2_hz: float
    f3_hz: float
    bandwidths_hz: Tuple[float, float, float]
    confidences: Tuple[float, float, float]


@dataclass(frozen=True)
class FormantTrack:
    """Formant trajectories and quality metrics across frames."""

    times_s: np.ndarray
    f1_hz: np.ndarray
    f2_hz: np.ndarray
    f3_hz: np.ndarray
    bandwidths_hz: np.ndarray
    confidences: np.ndarray


def _smooth_spectrum(spectrum: np.ndarray, kernel_bins: int) -> np.ndarray:
    if kernel_bins <= 1:
        return spectrum
    kernel = np.ones(int(kernel_bins), dtype=np.float32)
    kernel /= float(np.sum(kernel))
    return np.apply_along_axis(lambda m: np.convolve(m, kernel, mode="same"), 0, spectrum)


def _peak_bandwidth(
    magnitude: np.ndarray,
    frequencies: np.ndarray,
    peak_frequency: float,
    peak_amplitude: float,
) -> float:
    if peak_frequency <= 0.0 or peak_amplitude <= 0.0:
        return 0.0
    idx = int(np.argmin(np.abs(frequencies - peak_frequency)))
    threshold = peak_amplitude / np.sqrt(2.0)
    left = idx
    while left > 0 and magnitude[left] >= threshold:
        left -= 1
    right = idx
    while right < magnitude.size - 1 and magnitude[right] >= threshold:
        right += 1
    if right <= left:
        return 0.0
    return float(frequencies[right] - frequencies[left])


def _band_confidence(magnitude: np.ndarray, band_mask: np.ndarray, peak_amplitude: float) -> float:
    if not np.any(band_mask):
        return 0.0
    band_mean = float(np.mean(magnitude[band_mask]))
    return float(peak_amplitude / (band_mean + 1e-12))


def _select_peak(
    peaks: Sequence,
    band: Tuple[float, float],
    min_frequency: float,
) -> Optional[Tuple[float, float]]:
    band_min, band_max = band
    candidates = [p for p in peaks if band_min <= p.frequency <= band_max and p.frequency > min_frequency]
    if not candidates:
        return None
    best = max(candidates, key=lambda p: p.amplitude)
    return float(best.frequency), float(best.amplitude)


def estimate_formants_from_spectrum(
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    times: Optional[np.ndarray] = None,
    *,
    bands: Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]] = (
        (200.0, 1000.0),
        (700.0, 3000.0),
        (2000.0, 5000.0),
    ),
    min_db: float = -50.0,
    smoothing_bins: int = 5,
) -> FormantTrack:
    """Estimate F1/F2/F3 trajectories from a magnitude spectrogram.

    Args:
        spectrum: Magnitude spectrogram (freq x time).
        frequencies: Frequency grid (Hz) aligned with spectrum rows.
        times: Optional time vector in seconds (length = n_frames).
        bands: Frequency bands for (F1, F2, F3) search in Hz.
        min_db: Relative peak threshold for peak detection.
        smoothing_bins: Moving-average bins along frequency axis.
    """
    spectrum = np.asarray(spectrum, dtype=np.float32)
    frequencies = np.asarray(frequencies, dtype=np.float32)
    if spectrum.ndim != 2:
        raise ValueError("spectrum must be 2D (freq x time)")
    if frequencies.size != spectrum.shape[0]:
        raise ValueError("frequencies length must match spectrum rows")
    n_frames = spectrum.shape[1]
    if times is None:
        times = np.arange(n_frames, dtype=np.float32)
    else:
        times = np.asarray(times, dtype=np.float32)
    if times.shape[0] != n_frames:
        raise ValueError("times length must match spectrum columns")

    smoothed = _smooth_spectrum(spectrum, smoothing_bins)

    f1 = np.zeros(n_frames, dtype=np.float32)
    f2 = np.zeros(n_frames, dtype=np.float32)
    f3 = np.zeros(n_frames, dtype=np.float32)
    bandwidths = np.zeros((n_frames, 3), dtype=np.float32)
    confidences = np.zeros((n_frames, 3), dtype=np.float32)

    for t in range(n_frames):
        mag = smoothed[:, t]
        peaks = _find_peaks(mag, frequencies, min_db=min_db)
        prev_f = 0.0
        selections: List[Optional[Tuple[float, float]]] = []
        for band in bands:
            choice = _select_peak(peaks, band, prev_f)
            selections.append(choice)
            if choice is not None:
                prev_f = choice[0]

        for idx, (band, choice) in enumerate(zip(bands, selections)):
            if choice is None:
                continue
            freq, amp = choice
            band_mask = (frequencies >= band[0]) & (frequencies <= band[1])
            bandwidths[t, idx] = _peak_bandwidth(mag, frequencies, freq, amp)
            confidences[t, idx] = _band_confidence(mag, band_mask, amp)
            if idx == 0:
                f1[t] = freq
            elif idx == 1:
                f2[t] = freq
            else:
                f3[t] = freq

    return FormantTrack(
        times_s=times,
        f1_hz=f1,
        f2_hz=f2,
        f3_hz=f3,
        bandwidths_hz=bandwidths,
        confidences=confidences,
    )


def estimate_formants_from_audio(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 4096,
    hop_length: int = 512,
    target_sr: int = 44100,
    preprocess: bool = True,
    bands: Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]] = (
        (200.0, 1000.0),
        (700.0, 3000.0),
        (2000.0, 5000.0),
    ),
    min_db: float = -50.0,
    smoothing_bins: int = 5,
) -> FormantTrack:
    """Estimate formants directly from audio by computing an STFT."""
    if preprocess:
        result = preprocess_audio(audio, sample_rate, target_sr=target_sr)
        audio = result.audio
        sample_rate = int(result.sample_rate)
    stft = compute_stft(audio, sample_rate=sample_rate, n_fft=n_fft, hop_length=hop_length)
    return estimate_formants_from_spectrum(
        stft.spectrum,
        stft.frequencies,
        times=stft.times,
        bands=bands,
        min_db=min_db,
        smoothing_bins=smoothing_bins,
    )


def track_to_frames(track: FormantTrack) -> List[FormantFrame]:
    """Convert a FormantTrack to a list of FormantFrame objects."""
    frames: List[FormantFrame] = []
    for idx, time_s in enumerate(track.times_s):
        bandwidths = tuple(float(x) for x in track.bandwidths_hz[idx])
        confidences = tuple(float(x) for x in track.confidences[idx])
        frames.append(
            FormantFrame(
                time_s=float(time_s),
                f1_hz=float(track.f1_hz[idx]),
                f2_hz=float(track.f2_hz[idx]),
                f3_hz=float(track.f3_hz[idx]),
                bandwidths_hz=bandwidths,
                confidences=confidences,
            )
        )
    return frames


__all__ = [
    "FormantFrame",
    "FormantTrack",
    "estimate_formants_from_audio",
    "estimate_formants_from_spectrum",
    "track_to_frames",
]
