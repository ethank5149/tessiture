"""Harmonic peak detection helpers for Phase 2 analysis.

Example:
    frames = detect_harmonics(spectrum, frequencies)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

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


def _find_peaks(magnitude: np.ndarray, freqs: np.ndarray, min_db: float = -60.0) -> List[Peak]:
    """Find spectral peaks in a magnitude spectrum.

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
            peaks.append(Peak(float(freqs[i]), float(mag[i])))
    return peaks


def _match_harmonics(
    peaks: Sequence[Peak],
    f0: float,
    n_harmonics: int,
    freq_tolerance: float,
) -> List[Peak]:
    """Match detected peaks to harmonic targets."""
    matched: List[Peak] = []
    if not peaks:
        return matched
    peak_freqs = np.array([p.frequency for p in peaks], dtype=np.float32)
    peak_amps = np.array([p.amplitude for p in peaks], dtype=np.float32)
    for h in range(1, n_harmonics + 1):
        target = f0 * h
        idx = np.argmin(np.abs(peak_freqs - target))
        if abs(float(peak_freqs[idx]) - target) <= freq_tolerance:
            matched.append(Peak(float(peak_freqs[idx]), float(peak_amps[idx])))
    return matched


def detect_harmonics(
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    n_harmonics: int = 4,
    freq_tolerance: float = 5.0,
    min_db: float = -60.0,
    max_candidates: int = 6,
) -> List[HarmonicFrame]:
    """Detect harmonic candidates for each frame in a magnitude spectrogram.

    Args:
        spectrum: Magnitude spectrogram (freq x time).
        frequencies: Frequency vector aligned with spectrum rows.
        n_harmonics: Number of harmonics to score.
        freq_tolerance: Frequency tolerance in Hz when matching harmonics.
        min_db: Minimum relative threshold for peak detection.
        max_candidates: Maximum number of fundamental candidates per frame.

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
            matched = _match_harmonics(peaks, peak.frequency, n_harmonics, freq_tolerance)
            if not matched:
                continue
            weights = np.array([1.0 / (i + 1) for i in range(len(matched))], dtype=np.float32)
            amps = np.array([p.amplitude for p in matched], dtype=np.float32)
            score = float(np.sum(weights * amps) / (np.sum(weights) + 1e-12))
            candidates.append(
                HarmonicCandidate(
                    f0=float(peak.frequency),
                    score=score,
                    harmonics=matched,
                )
            )
        candidates.sort(key=lambda c: c.score, reverse=True)
        frames.append(HarmonicFrame(time_index=t, candidates=candidates))
    return frames
