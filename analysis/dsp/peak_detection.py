"""Harmonic peak detection helpers for Phase 2 analysis.

Example:
    frames = detect_harmonics(spectrum, frequencies)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np


@dataclass
class Peak:
    frequency: float
    amplitude: float


@dataclass
class HarmonicCandidate:
    f0: float
    score: float
    harmonics: List[Peak]


@dataclass
class HarmonicFrame:
    time_index: int
    candidates: List[HarmonicCandidate]


def _find_peaks(magnitude: np.ndarray, freqs: np.ndarray, min_db: float = -40.0) -> List[Peak]:
    """Find spectral peaks in a magnitude spectrum using parabolic interpolation.

    Args:
        magnitude: Magnitude spectrum (1D).
        freqs: Frequency bin centers.
        min_db: Minimum relative dB threshold compared to max.
    """
    if magnitude.size == 0:
        return []
    mag = np.asarray(magnitude, dtype=np.float32)
    freqs = np.asarray(freqs, dtype=np.float32)
    max_mag = float(np.max(mag)) if mag.size else 0.0
    if max_mag <= 0.0:
        return []
    threshold = max_mag * (10.0 ** (min_db / 20.0))
    peaks: List[Peak] = []
    for i in range(1, mag.size - 1):
        if mag[i] >= threshold and mag[i] > mag[i - 1] and mag[i] >= mag[i + 1]:
            # Parabolic (quadratic) interpolation for sub-bin frequency accuracy
            # Smith, "Spectral Audio Signal Processing", 2011
            alpha = float(mag[i - 1])
            beta = float(mag[i])
            gamma = float(mag[i + 1])
            denom = alpha - 2.0 * beta + gamma
            if abs(denom) > 1e-12:
                delta = 0.5 * (alpha - gamma) / denom
            else:
                delta = 0.0
            delta = float(np.clip(delta, -0.5, 0.5))  # stay within bin
            bin_spacing = float(freqs[1] - freqs[0]) if freqs.size > 1 else 1.0
            interp_freq = float(freqs[i]) + delta * bin_spacing
            interp_mag = beta - 0.25 * (alpha - gamma) * delta
            peaks.append(Peak(float(interp_freq), float(max(interp_mag, 0.0))))
    return peaks


def _match_harmonics(
    peaks: Sequence[Peak],
    f0: float,
    n_harmonics: int,
    freq_tolerance: float,
    tolerance_mode: str = "cents",
) -> List[Tuple[int, Peak]]:
    """Match detected peaks to harmonic targets.

    Returns:
        List of (harmonic_number, Peak) tuples for each matched harmonic.
    """
    matched: List[Tuple[int, Peak]] = []
    if not peaks:
        return matched
    peak_freqs = np.array([p.frequency for p in peaks], dtype=np.float32)
    peak_amps = np.array([p.amplitude for p in peaks], dtype=np.float32)
    for h in range(1, n_harmonics + 1):
        target = f0 * h
        if tolerance_mode == "cents":
            # Convert cents to Hz at the target frequency
            tol_hz = target * (2.0 ** (freq_tolerance / 1200.0) - 1.0)
        else:
            tol_hz = freq_tolerance
        idx = np.argmin(np.abs(peak_freqs - target))
        if abs(float(peak_freqs[idx]) - target) <= tol_hz:
            matched.append((h, Peak(float(peak_freqs[idx]), float(peak_amps[idx]))))
    return matched


def detect_harmonics(
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    n_harmonics: int = 4,
    freq_tolerance: float = 50.0,
    min_db: float = -40.0,
    max_candidates: int = 6,
    tolerance_mode: str = "cents",
) -> List[HarmonicFrame]:
    """Detect harmonic candidates for each frame in a magnitude spectrogram.

    Args:
        spectrum: Magnitude spectrogram (freq x time).
        frequencies: Frequency vector aligned with spectrum rows.
        n_harmonics: Number of harmonics to score.
        freq_tolerance: Frequency tolerance when matching harmonics. Units depend
            on tolerance_mode: cents (default) or Hz.
        min_db: Minimum relative threshold for peak detection (default -40 dB).
        max_candidates: Maximum number of fundamental candidates per frame.
        tolerance_mode: ``"cents"`` (default, proportional) or ``"hz"`` (fixed Hz).

    Returns:
        List of HarmonicFrame objects.

    Example:
        frames = detect_harmonics(spectrum, frequencies, n_harmonics=5)
    """
    spectrum = np.asarray(spectrum, dtype=np.float32)
    frequencies = np.asarray(frequencies, dtype=np.float32)
    if spectrum.ndim != 2:
        raise ValueError("spectrum must be 2D (freq x time)")

    frames: List[HarmonicFrame] = []
    for t in range(spectrum.shape[1]):
        mag = spectrum[:, t]
        peaks = _find_peaks(mag, frequencies, min_db=min_db)
        # Sort by amplitude and select candidate fundamentals
        peaks_sorted = sorted(peaks, key=lambda p: p.amplitude, reverse=True)
        candidates: List[HarmonicCandidate] = []
        for peak in peaks_sorted[:max_candidates]:
            harmonic_pairs = _match_harmonics(
                peaks, peak.frequency, n_harmonics, freq_tolerance, tolerance_mode
            )
            if not harmonic_pairs:
                continue
            # Weight by 1/h² (glottal source model: energy falls as 1/h²)
            h_nums = np.array([h for h, _ in harmonic_pairs], dtype=np.float32)
            amps = np.array([p.amplitude for _, p in harmonic_pairs], dtype=np.float32)
            weights = 1.0 / (h_nums ** 2)
            score = float(np.sum(weights * amps) / (np.sum(weights) + 1e-12))
            matched_peaks = [p for _, p in harmonic_pairs]
            candidates.append(
                HarmonicCandidate(
                    f0=float(peak.frequency),
                    score=score,
                    harmonics=matched_peaks,
                )
            )
        candidates.sort(key=lambda c: c.score, reverse=True)
        frames.append(HarmonicFrame(time_index=t, candidates=candidates))
    return frames
