"""Pitch-class histogram utilities for key detection."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

import numpy as np


Observation = Tuple[float, float] | float


def _iter_observations(
    observations: Sequence[Observation],
    weights: Optional[Sequence[float]] = None,
) -> Iterable[Tuple[float, float]]:
    if weights is not None:
        if len(weights) != len(observations):
            raise ValueError("weights length must match observations")
        for note, weight in zip(observations, weights):
            yield float(note), float(weight)
        return

    for obs in observations:
        if isinstance(obs, (tuple, list)) and len(obs) == 2:
            note, weight = obs
            yield float(note), float(weight)
        else:
            yield float(obs), 1.0


def normalize_histogram(histogram: np.ndarray) -> np.ndarray:
    """Normalize a pitch-class histogram to sum to 1."""
    hist = np.asarray(histogram, dtype=np.float64)
    total = float(np.sum(hist))
    if total > 0.0:
        return hist / total
    return hist


def build_pitch_class_histogram(
    observations: Sequence[Observation],
    *,
    weights: Optional[Sequence[float]] = None,
    input_unit: str = "midi",
    normalize: bool = True,
) -> np.ndarray:
    """Compute a weighted pitch-class histogram from observations.

    Args:
        observations: Sequence of MIDI notes, pitch classes, or (note, weight) pairs.
        weights: Optional weights aligned with observations.
        input_unit: "midi" for MIDI note numbers, or "pc" for pitch classes.
        normalize: Whether to normalize the histogram to sum to 1.

    Returns:
        Array of length 12 with pitch-class weights.
    """
    if input_unit not in {"midi", "pc"}:
        raise ValueError("input_unit must be 'midi' or 'pc'")

    histogram = np.zeros(12, dtype=np.float64)
    if not observations:
        return histogram

    for note, weight in _iter_observations(observations, weights=weights):
        if not np.isfinite(note) or not np.isfinite(weight):
            continue
        if input_unit == "midi":
            pitch_class = int(round(note)) % 12
        else:
            pitch_class = int(round(note)) % 12
        histogram[pitch_class] += float(weight)

    return normalize_histogram(histogram) if normalize else histogram


__all__ = [
    "Observation",
    "build_pitch_class_histogram",
    "normalize_histogram",
]