"""Confidence model fitting utilities."""

from __future__ import annotations

from typing import Callable, Dict

import numpy as np


def _prepare_grid(
    freq_bins: np.ndarray, snr_bins: np.ndarray, probabilities: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Validate and align frequency/SNR grids with probability values."""

    freq_bins = np.asarray(freq_bins, dtype=float)
    snr_bins = np.asarray(snr_bins, dtype=float)
    probabilities = np.asarray(probabilities, dtype=float)

    if freq_bins.ndim != 1 or snr_bins.ndim != 1:
        raise ValueError("Frequency and SNR bins must be 1D arrays.")
    if probabilities.shape != (freq_bins.size, snr_bins.size):
        raise ValueError("Probabilities must be shaped (n_freq_bins, n_snr_bins).")
    if not np.all(np.isfinite(freq_bins)) or not np.all(np.isfinite(snr_bins)):
        raise ValueError("Bins must contain finite values.")
    if not np.all(np.isfinite(probabilities)):
        raise ValueError("Probabilities must contain finite values.")

    if freq_bins.size < 2 or snr_bins.size < 2:
        raise ValueError("Frequency and SNR bins must have at least two points.")

    freq_sort = np.argsort(freq_bins)
    snr_sort = np.argsort(snr_bins)
    freq_bins_sorted = freq_bins[freq_sort]
    snr_bins_sorted = snr_bins[snr_sort]
    probabilities_sorted = probabilities[np.ix_(freq_sort, snr_sort)]

    return freq_bins_sorted, snr_bins_sorted, probabilities_sorted


def build_confidence_surface(
    freq_bins: np.ndarray, snr_bins: np.ndarray, probabilities: np.ndarray
) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    """Build a bilinear interpolation model for detection probability.

    Args:
        freq_bins: 1D array of frequency bin centers in Hz.
        snr_bins: 1D array of SNR bin centers in dB.
        probabilities: 2D grid of detection probabilities with shape
            (len(freq_bins), len(snr_bins)).

    Returns:
        Callable that maps query (frequency, SNR) arrays to detection probability.
    """

    freq_bins_sorted, snr_bins_sorted, probs_sorted = _prepare_grid(
        freq_bins, snr_bins, probabilities
    )

    def _surface(query_freq: np.ndarray, query_snr: np.ndarray) -> np.ndarray:
        freq = np.asarray(query_freq, dtype=float)
        snr = np.asarray(query_snr, dtype=float)
        if freq.shape != snr.shape:
            raise ValueError("Frequency and SNR query arrays must have matching shapes.")
        if freq.size == 0:
            return np.asarray([], dtype=float)

        freq_clipped = np.clip(freq, freq_bins_sorted[0], freq_bins_sorted[-1])
        snr_clipped = np.clip(snr, snr_bins_sorted[0], snr_bins_sorted[-1])

        freq_idx = np.searchsorted(freq_bins_sorted, freq_clipped, side="right") - 1
        snr_idx = np.searchsorted(snr_bins_sorted, snr_clipped, side="right") - 1
        freq_idx = np.clip(freq_idx, 0, freq_bins_sorted.size - 2)
        snr_idx = np.clip(snr_idx, 0, snr_bins_sorted.size - 2)

        f0 = freq_bins_sorted[freq_idx]
        f1 = freq_bins_sorted[freq_idx + 1]
        s0 = snr_bins_sorted[snr_idx]
        s1 = snr_bins_sorted[snr_idx + 1]

        f_alpha = np.where(f1 == f0, 0.0, (freq_clipped - f0) / (f1 - f0))
        s_alpha = np.where(s1 == s0, 0.0, (snr_clipped - s0) / (s1 - s0))

        p00 = probs_sorted[freq_idx, snr_idx]
        p10 = probs_sorted[freq_idx + 1, snr_idx]
        p01 = probs_sorted[freq_idx, snr_idx + 1]
        p11 = probs_sorted[freq_idx + 1, snr_idx + 1]

        p0 = p00 * (1.0 - f_alpha) + p10 * f_alpha
        p1 = p01 * (1.0 - f_alpha) + p11 * f_alpha
        return p0 * (1.0 - s_alpha) + p1 * s_alpha

    return _surface


def suggest_detection_thresholds(
    confidence_surface: Callable[[np.ndarray, np.ndarray], np.ndarray]
) -> Dict[str, float]:
    """Suggest detection thresholds based on a confidence surface.

    Placeholder implementation: returns fixed defaults suitable for Phase 1.3
    calibration scaffolding. Consumers can replace this with an optimization
    routine later.
    """

    _ = confidence_surface
    return {
        "min_confidence": 0.5,
        "min_snr_db": 3.0,
        "min_probability": 0.5,
    }


__all__ = ["build_confidence_surface", "suggest_detection_thresholds"]
