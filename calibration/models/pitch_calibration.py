"""Pitch calibration model fitting utilities."""

from __future__ import annotations

from typing import Callable

import numpy as np


def _prepare_inputs(frequencies: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Validate and align frequency/value arrays."""

    if frequencies.size == 0 or values.size == 0:
        raise ValueError("Frequencies and values must be non-empty arrays.")
    if frequencies.shape != values.shape:
        raise ValueError("Frequencies and values must have matching shapes.")
    if not np.all(np.isfinite(frequencies)):
        raise ValueError("Frequencies must be finite numbers.")
    if not np.all(np.isfinite(values)):
        raise ValueError("Values must be finite numbers.")
    sort_idx = np.argsort(frequencies)
    return frequencies[sort_idx], values[sort_idx]


def fit_pitch_bias(frequencies: np.ndarray, bias: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    """Fit a piecewise-linear pitch bias correction over frequency.

    Args:
        frequencies: Frequency bin centers in Hz.
        bias: Estimated pitch bias (cents) for each bin.

    Returns:
        Callable that maps query frequencies (Hz) to bias corrections (cents).
    """

    freq_sorted, bias_sorted = _prepare_inputs(
        np.asarray(frequencies, dtype=float), np.asarray(bias, dtype=float)
    )

    def _bias_model(query_frequencies: np.ndarray) -> np.ndarray:
        query = np.asarray(query_frequencies, dtype=float)
        if query.size == 0:
            return np.asarray([], dtype=float)
        return np.interp(query, freq_sorted, bias_sorted, left=bias_sorted[0], right=bias_sorted[-1])

    return _bias_model


def fit_pitch_variance(
    frequencies: np.ndarray, variance: np.ndarray
) -> Callable[[np.ndarray], np.ndarray]:
    """Fit a piecewise-linear pitch variance lookup over frequency.

    Args:
        frequencies: Frequency bin centers in Hz.
        variance: Estimated pitch variance (cents^2) for each bin.

    Returns:
        Callable that maps query frequencies (Hz) to variance values (cents^2).
    """

    freq_sorted, var_sorted = _prepare_inputs(
        np.asarray(frequencies, dtype=float), np.asarray(variance, dtype=float)
    )

    def _variance_model(query_frequencies: np.ndarray) -> np.ndarray:
        query = np.asarray(query_frequencies, dtype=float)
        if query.size == 0:
            return np.asarray([], dtype=float)
        return np.interp(query, freq_sorted, var_sorted, left=var_sorted[0], right=var_sorted[-1])

    return _variance_model


__all__ = ["fit_pitch_bias", "fit_pitch_variance"]
