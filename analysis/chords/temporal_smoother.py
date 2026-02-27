"""Temporal smoothing utilities for chord sequences."""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np


def viterbi_smooth(
    chord_names: Sequence[str],
    probability_frames: np.ndarray,
    *,
    transition_penalty: float = 0.2,
) -> List[str]:
    """Smooth a chord probability sequence with a simple transition penalty.

    Args:
        chord_names: Ordered chord labels matching probability_frames columns.
        probability_frames: Array of shape (T, N) with probabilities per frame.
        transition_penalty: Penalty applied when changing chords (log-domain).

    Returns:
        List of smoothed chord labels for each frame.
    """
    if probability_frames.size == 0:
        return []

    probs = np.asarray(probability_frames, dtype=np.float64)
    probs = np.clip(probs, 1e-12, 1.0)
    log_probs = np.log(probs)

    time_steps, num_chords = log_probs.shape
    dp = np.full((time_steps, num_chords), -np.inf, dtype=np.float64)
    back = np.zeros((time_steps, num_chords), dtype=np.int64)

    dp[0] = log_probs[0]
    penalty = float(transition_penalty)

    for t in range(1, time_steps):
        prev = dp[t - 1]
        for j in range(num_chords):
            transition_cost = prev - penalty
            transition_cost[j] = prev[j]
            best_prev = int(np.argmax(transition_cost))
            dp[t, j] = log_probs[t, j] + transition_cost[best_prev]
            back[t, j] = best_prev

    path = [int(np.argmax(dp[-1]))]
    for t in range(time_steps - 1, 0, -1):
        path.append(int(back[t, path[-1]]))
    path.reverse()
    return [chord_names[idx] for idx in path]


def smooth_probability_sequence(
    probability_sequence: Sequence[Dict[str, float]],
    *,
    transition_penalty: float = 0.2,
) -> List[str]:
    """Smooth a sequence of chord probability dictionaries.

    Args:
        probability_sequence: List of probability maps per frame.
        transition_penalty: Penalty applied when changing chords.

    Returns:
        Smoothed chord labels for each frame.
    """
    if not probability_sequence:
        return []

    chord_set = sorted({name for frame in probability_sequence for name in frame.keys()})
    if not chord_set:
        return []

    frames = np.zeros((len(probability_sequence), len(chord_set)), dtype=np.float64)
    for i, frame in enumerate(probability_sequence):
        for j, name in enumerate(chord_set):
            frames[i, j] = float(frame.get(name, 0.0))
        total = float(np.sum(frames[i]))
        if total > 0:
            frames[i] /= total

    return viterbi_smooth(chord_set, frames, transition_penalty=transition_penalty)


__all__ = [
    "smooth_probability_sequence",
    "viterbi_smooth",
]
