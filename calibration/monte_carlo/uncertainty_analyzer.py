"""Uncertainty analysis utilities for Monte Carlo calibration."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

import numpy as np


def _extract_reference_frequencies(results: Iterable[Mapping[str, Any]]) -> List[float]:
    """Extract reference frequencies from result metadata."""

    frequencies: List[float] = []
    for item in results:
        metadata = item.get("metadata", {}) if isinstance(item, Mapping) else {}
        base = metadata.get("note_frequencies_hz")
        if base is None:
            base = metadata.get("f0_hz")

        if isinstance(base, (list, tuple, np.ndarray)):
            for val in base:
                try:
                    frequencies.append(float(val))
                except (TypeError, ValueError):
                    frequencies.append(float("nan"))
        elif base is not None:
            try:
                frequencies.append(float(base))
            except (TypeError, ValueError):
                frequencies.append(float("nan"))
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

    def _as_sequence(value: Any) -> List[Any]:
        if isinstance(value, (list, tuple, np.ndarray)):
            return list(value)
        if value is None:
            return []
        return [value]

    results_list = list(results)
    frequencies = _extract_reference_frequencies(results_list)
    pitch_errors = _extract_pitch_errors(results_list)

    freq_values = np.asarray(frequencies, dtype=float) if frequencies else np.asarray([], dtype=float)
    valid_freq_values = freq_values[np.isfinite(freq_values) & (freq_values > 0.0)]

    if valid_freq_values.size:
        min_freq = float(np.min(valid_freq_values))
        max_freq = float(np.max(valid_freq_values))
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
        aligned_frequencies: List[float] = []
        aligned_pitch_errors: List[float] = []

        for item in results_list:
            if not isinstance(item, Mapping):
                continue

            metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), Mapping) else {}
            freq_raw = metadata.get("note_frequencies_hz")
            if freq_raw is None:
                freq_raw = metadata.get("f0_hz")
            error_raw = item.get("pitch_error_cents")

            freq_seq = _as_sequence(freq_raw)
            error_seq = _as_sequence(error_raw)
            if not error_seq:
                continue
            if len(freq_seq) == 1 and len(error_seq) > 1:
                freq_seq = freq_seq * len(error_seq)

            pair_count = min(len(freq_seq), len(error_seq))
            for idx in range(pair_count):
                try:
                    freq_val = float(freq_seq[idx])
                except (TypeError, ValueError):
                    freq_val = float("nan")
                try:
                    error_val = float(error_seq[idx])
                except (TypeError, ValueError):
                    continue

                if not np.isfinite(error_val):
                    continue
                if not np.isfinite(freq_val) or freq_val <= 0.0:
                    continue

                aligned_frequencies.append(freq_val)
                aligned_pitch_errors.append(error_val)

        if aligned_frequencies:
            aligned_freq_arr = np.asarray(aligned_frequencies, dtype=float)
            aligned_err_arr = np.asarray(aligned_pitch_errors, dtype=float)

            counts, _ = np.histogram(aligned_freq_arr, bins=bins)
            pitch_bias = np.full_like(bin_centers, np.nan, dtype=float)
            pitch_variance = np.full_like(bin_centers, np.nan, dtype=float)

            freq_assign = np.digitize(aligned_freq_arr, bins=bins, right=False)
            freq_assign[freq_assign == len(bins)] = len(bins) - 1

            for idx in range(1, len(bins)):
                mask = freq_assign == idx
                if not np.any(mask):
                    continue
                values = aligned_err_arr[mask]
                pitch_bias[idx - 1] = float(np.mean(values))
                pitch_variance[idx - 1] = float(np.var(values))
        else:
            pitch_bias = np.full_like(bin_centers, np.nan, dtype=float)
            pitch_variance = np.full_like(bin_centers, np.nan, dtype=float)
            counts = np.zeros_like(bin_centers, dtype=int)

    return {
        "frequency_bins_hz": bins.tolist(),
        "frequency_bin_centers_hz": bin_centers.tolist(),
        "pitch_bias_cents": np.nan_to_num(pitch_bias, nan=0.0).tolist(),
        "pitch_variance_cents2": np.nan_to_num(pitch_variance, nan=0.0).tolist(),
        "sample_counts": counts.tolist(),
        # detection_probability and confidence_surface are reserved for a future calibration
        # phase that will compute the confidence surface from Monte Carlo results.
        # See calibration/models/confidence_models.py for the surface model API.
        "detection_probability": None,
        "confidence_surface": None,
    }


__all__ = ["summarize_uncertainty"]
