"""Smoothing utilities for key probability sequences."""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

import numpy as np

from analysis.chords._viterbi_shared import _viterbi_smooth_sequences


def _moving_average(frames: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return frames
    kernel = np.ones(int(window), dtype=np.float64)
    kernel /= float(np.sum(kernel))
    smoothed = np.zeros_like(frames, dtype=np.float64)
    for i in range(frames.shape[1]):
        smoothed[:, i] = np.convolve(frames[:, i], kernel, mode="same")
    return smoothed


def viterbi_smooth(
    key_labels: Sequence[str],
    probability_frames: np.ndarray,
    *,
    transition_penalty: float = 0.15,
) -> List[str]:
    """Smooth key probabilities with a simple transition penalty Viterbi pass."""
    return _viterbi_smooth_sequences(
        list(key_labels), probability_frames, transition_penalty=transition_penalty
    )


def smooth_key_probabilities(
    probability_sequence: Sequence[Dict[str, float]],
    *,
    method: str = "viterbi",
    transition_penalty: float = 0.15,
    window: int = 3,
) -> List[str]:
    """Smooth a sequence of key probability dictionaries.

    Args:
        probability_sequence: List of probability maps per frame.
        method: "viterbi" or "moving_average".
        transition_penalty: Penalty for key changes in Viterbi smoothing.
        window: Window length for moving average smoothing.

    Returns:
        Smoothed key labels for each frame.
    """
    if not probability_sequence:
        return []

    key_set = sorted({name for frame in probability_sequence for name in frame.keys()})
    if not key_set:
        return []

    frames = np.zeros((len(probability_sequence), len(key_set)), dtype=np.float64)
    for i, frame in enumerate(probability_sequence):
        for j, name in enumerate(key_set):
            frames[i, j] = float(frame.get(name, 0.0))
        total = float(np.sum(frames[i]))
        if total > 0:
            frames[i] /= total

    if method == "moving_average":
        smoothed = _moving_average(frames, window=max(int(window), 1))
        best_indices = np.argmax(smoothed, axis=1)
        return [key_set[int(idx)] for idx in best_indices]
    if method != "viterbi":
        raise ValueError("method must be 'viterbi' or 'moving_average'")

    return viterbi_smooth(key_set, frames, transition_penalty=transition_penalty)


__all__ = [
    "smooth_key_probabilities",
    "viterbi_smooth",
]