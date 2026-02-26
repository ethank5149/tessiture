"""Uncertainty analysis utilities for Monte Carlo calibration."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

import numpy as np


def _extract_reference_frequencies(results: Iterable[Mapping[str, Any]]) -> List[float]:
    """Extract reference frequencies from result metadata."""

    frequencies: List[float] = []
    for item in results:
        metadata = item.get("metadata", {}) if isinstance(item, Mapping) else {}
        base = metadata.get("note_frequencies_hz") or metadata.get("f0_hz")
        if isinstance(base, (list, tuple, np.ndarray)):
            frequencies.extend([float(val) for val in base if val is not None])
        elif base is not None:
            frequencies.append(float(base))
    return frequencies


def _extract_pitch_errors(results: Iterable[Mapping[str, Any]]) -> np.ndarray:
    """Extract pitch error list if provided in result dictionaries."""

    errors: List[float] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        pitch_error = item.get("pitch_error_cents")
        if pitch_error is None:
            continue
        if isinstance(pitch_error, (list, tuple, np.ndarray)):
            errors.extend([float(val) for val in pitch_error])
        else:
            errors.append(float(pitch_error))
    return np.asarray(errors, dtype=float)


def summarize_uncertainty(results: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Summarize uncertainty metrics across Monte Carlo results.

    Args:
        results: Iterable of Monte Carlo result dictionaries.

    Returns:
        Dictionary with pitch bias/variance binned by frequency and placeholders
        for detection probability surfaces.
    """

    results_list = list(results)
    frequencies = _extract_reference_frequencies(results_list)
    pitch_errors = _extract_pitch_errors(results_list)

    if frequencies:
        freq_values = np.asarray(frequencies, dtype=float)
        min_freq = float(np.nanmin(freq_values))
        max_freq = float(np.nanmax(freq_values))
        n_bins = 12
        if min_freq == max_freq:
            bins = np.array([min_freq, max_freq + 1.0], dtype=float)
        else:
            bins = np.linspace(min_freq, max_freq, n_bins + 1, dtype=float)
    else:
        bins = np.linspace(80.0, 2000.0, 13, dtype=float)

    bin_centers = 0.5 * (bins[:-1] + bins[1:])

    if pitch_errors.size == 0:
        pitch_bias = np.zeros_like(bin_centers)
        pitch_variance = np.zeros_like(bin_centers)
        counts = np.zeros_like(bin_centers, dtype=int)
    else:
        counts, _ = np.histogram(frequencies if frequencies else np.zeros_like(pitch_errors), bins=bins)
        pitch_bias = np.full_like(bin_centers, np.nan, dtype=float)
        pitch_variance = np.full_like(bin_centers, np.nan, dtype=float)
        freq_assign = np.digitize(
            frequencies if frequencies else np.zeros_like(pitch_errors), bins=bins
        )
        for idx in range(1, len(bins)):
            mask = freq_assign == idx
            if not np.any(mask):
                continue
            values = pitch_errors[: np.sum(mask)] if pitch_errors.size >= np.sum(mask) else pitch_errors
            pitch_bias[idx - 1] = float(np.mean(values))
            pitch_variance[idx - 1] = float(np.var(values))

    return {
        "frequency_bins_hz": bins.tolist(),
        "frequency_bin_centers_hz": bin_centers.tolist(),
        "pitch_bias_cents": np.nan_to_num(pitch_bias, nan=0.0).tolist(),
        "pitch_variance_cents2": np.nan_to_num(pitch_variance, nan=0.0).tolist(),
        "sample_counts": counts.tolist(),
        "detection_probability": None,
        "confidence_surface": None,
    }


__all__ = ["summarize_uncertainty"]
