"""Shared Viterbi smoothing implementation for chord and key sequences."""
from __future__ import annotations

from typing import List, Sequence

import numpy as np


def _viterbi_smooth_sequences(
    labels: Sequence[str],
    probability_frames: np.ndarray,
    *,
    transition_penalty: float,
) -> List[str]:
    """Internal Viterbi smoothing with transition penalty (log-domain).

    Args:
        labels: Ordered label strings matching probability_frames columns.
        probability_frames: Array (T, N) with per-frame probabilities.
        transition_penalty: Log-domain penalty for label changes.

    Returns:
        List of smoothed labels, one per time step.
    """
    if probability_frames.size == 0:
        return []

    probs = np.asarray(probability_frames, dtype=np.float64)
    probs = np.clip(probs, 1e-12, 1.0)
    log_probs = np.log(probs)

    time_steps, num_labels = log_probs.shape
    dp = np.full((time_steps, num_labels), -np.inf, dtype=np.float64)
    back = np.zeros((time_steps, num_labels), dtype=np.int64)

    dp[0] = log_probs[0]
    penalty = float(transition_penalty)

    for t in range(1, time_steps):
        prev = dp[t - 1]
        for j in range(num_labels):
            transition_cost = prev - penalty
            transition_cost[j] = prev[j]
            best_prev = int(np.argmax(transition_cost))
            dp[t, j] = log_probs[t, j] + transition_cost[best_prev]
            back[t, j] = best_prev

    path = [int(np.argmax(dp[-1]))]
    for t in range(time_steps - 1, 0, -1):
        path.append(int(back[t, path[-1]]))
    path.reverse()
    return [labels[idx] for idx in path]
