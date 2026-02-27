"""Weighted vocal range utilities for tessitura analysis."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np


def _prepare_observations(
    pitches: Sequence[float],
    *,
    weights: Optional[Sequence[float]] = None,
    confidences: Optional[Sequence[float]] = None,
    uncertainties: Optional[Sequence[float]] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Validate and align pitch observations with optional weights/confidence."""

    values = np.asarray(pitches, dtype=float)
    if values.size == 0:
        raise ValueError("pitches must contain at least one value.")

    weights_array = (
        np.ones_like(values, dtype=float)
        if weights is None
        else np.asarray(weights, dtype=float)
    )
    if weights_array.shape != values.shape:
        raise ValueError("weights must match pitches length.")
    if np.any(weights_array < 0):
        raise ValueError("weights must be non-negative.")

    if confidences is not None:
        confidences_array = np.asarray(confidences, dtype=float)
        if confidences_array.shape != values.shape:
            raise ValueError("confidences must match pitches length.")
        if np.any(confidences_array < 0):
            raise ValueError("confidences must be non-negative.")
        weights_array = weights_array * confidences_array

    uncertainties_array = (
        np.zeros_like(values, dtype=float)
        if uncertainties is None
        else np.asarray(uncertainties, dtype=float)
    )
    if uncertainties_array.shape != values.shape:
        raise ValueError("uncertainties must match pitches length.")
    if np.any(uncertainties_array < 0):
        raise ValueError("uncertainties must be non-negative.")

    valid_mask = np.isfinite(values) & np.isfinite(weights_array) & np.isfinite(
        uncertainties_array
    )
    valid_mask &= weights_array > 0

    values = values[valid_mask]
    weights_array = weights_array[valid_mask]
    uncertainties_array = uncertainties_array[valid_mask]

    if values.size == 0:
        raise ValueError("No valid observations after filtering.")

    return values, weights_array, uncertainties_array


def compute_weighted_percentiles(
    pitches: Sequence[float],
    *,
    weights: Optional[Sequence[float]] = None,
    percentiles: Sequence[float] = (0.15, 0.85),
) -> Tuple[float, ...]:
    """Compute weighted percentiles for pitch observations.

    Args:
        pitches: Sequence of MIDI pitch values.
        weights: Optional per-observation weights.
        percentiles: Percentiles in [0, 1].
    """

    values, weight_values, _ = _prepare_observations(pitches, weights=weights)

    percentile_values = np.asarray(percentiles, dtype=float)
    if np.any(percentile_values < 0) or np.any(percentile_values > 1):
        raise ValueError("percentiles must be between 0 and 1.")

    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = weight_values[order]

    cumulative = np.cumsum(sorted_weights)
    total = cumulative[-1]
    cumulative = cumulative / max(total, np.finfo(float).eps)

    result = np.interp(percentile_values, cumulative, sorted_values)
    return tuple(float(val) for val in result)


def compute_range(
    pitches: Sequence[float],
    *,
    weights: Optional[Sequence[float]] = None,
) -> Tuple[float, float]:
    """Compute weighted min/max range for pitch observations."""

    values, _, _ = _prepare_observations(pitches, weights=weights)
    return float(np.min(values)), float(np.max(values))


def compute_extremum_confidence_intervals(
    pitches: Sequence[float],
    *,
    weights: Optional[Sequence[float]] = None,
    confidences: Optional[Sequence[float]] = None,
    uncertainties: Optional[Sequence[float]] = None,
    n_samples: int = 1000,
    ci: float = 0.95,
    rng: Optional[int | np.random.Generator] = None,
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Estimate confidence intervals for min/max notes via Monte Carlo sampling.

    Args:
        pitches: Sequence of MIDI pitch values (means).
        weights: Optional weights; used to filter invalid observations.
        confidences: Optional confidence multipliers for weights.
        uncertainties: Optional per-observation standard deviations (MIDI units).
        n_samples: Number of Monte Carlo samples to draw.
        ci: Confidence interval width in (0, 1).
        rng: Optional RNG seed or Generator for reproducibility.

    Returns:
        Tuple of (min_ci, max_ci) where each is (low, high).
    """
    values, _, uncertainty_values = _prepare_observations(
        pitches,
        weights=weights,
        confidences=confidences,
        uncertainties=uncertainties,
    )
    if n_samples <= 0:
        raise ValueError("n_samples must be positive.")
    if ci <= 0.0 or ci >= 1.0:
        raise ValueError("ci must be between 0 and 1.")

    generator = rng if isinstance(rng, np.random.Generator) else np.random.default_rng(rng)
    samples = generator.normal(
        loc=values[None, :],
        scale=uncertainty_values[None, :],
        size=(int(n_samples), values.size),
    )
    min_samples = np.min(samples, axis=1)
    max_samples = np.max(samples, axis=1)

    tail = (1.0 - float(ci)) / 2.0
    lower = float(100.0 * tail)
    upper = float(100.0 * (1.0 - tail))
    min_ci = tuple(float(val) for val in np.percentile(min_samples, [lower, upper]))
    max_ci = tuple(float(val) for val in np.percentile(max_samples, [lower, upper]))
    return min_ci, max_ci


def compute_comfort_band(
    pitches: Sequence[float],
    *,
    weights: Optional[Sequence[float]] = None,
    occupancy: float = 0.7,
) -> Tuple[float, float]:
    """Compute comfort band covering the given occupancy fraction."""

    if occupancy <= 0 or occupancy >= 1:
        raise ValueError("occupancy must be between 0 and 1.")

    tail = (1.0 - occupancy) / 2.0
    low, high = compute_weighted_percentiles(
        pitches, weights=weights, percentiles=(tail, 1.0 - tail)
    )
    return float(low), float(high)
