"""Lead voice path optimization for Phase 2 analysis.

Example:
    path = optimize_lead_voice(candidates)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from analysis.pitch.estimator import PitchFrame


@dataclass
class OptimizedPath:
    f0_hz: np.ndarray
    salience: np.ndarray
    path_indices: np.ndarray


def _transition_cost(prev_f0: float, curr_f0: float, penalty: float) -> float:
    if prev_f0 <= 0.0 or curr_f0 <= 0.0:
        return 0.0
    ratio = max(prev_f0, curr_f0) / min(prev_f0, curr_f0)
    return penalty * abs(np.log2(ratio))


def optimize_lead_voice(
    candidates: List[PitchFrame],
    alt_candidates: Optional[List[List[PitchFrame]]] = None,
    jump_penalty: float = 0.4,
) -> OptimizedPath:
    """Optimize pitch trajectory with Viterbi-like dynamic programming.

    Args:
        candidates: Primary pitch candidates per frame.
        alt_candidates: Optional list of alternative candidates per frame.
        jump_penalty: Penalty weight for pitch discontinuity (log-frequency space).

    Returns:
        OptimizedPath containing selected f0 and salience per frame.

    Example:
        path = optimize_lead_voice(candidates, jump_penalty=0.5)
    """
    n_frames = len(candidates)
    if n_frames == 0:
        return OptimizedPath(f0_hz=np.array([]), salience=np.array([]), path_indices=np.array([]))

    all_candidates: List[List[PitchFrame]] = []
    for i in range(n_frames):
        frame_list = [candidates[i]]
        if alt_candidates is not None and i < len(alt_candidates):
            frame_list += alt_candidates[i]
        all_candidates.append(frame_list)

    max_states = max(len(frame) for frame in all_candidates)
    scores = np.full((n_frames, max_states), -np.inf, dtype=np.float32)
    back = np.full((n_frames, max_states), -1, dtype=np.int32)

    # Initialize
    for s, cand in enumerate(all_candidates[0]):
        scores[0, s] = cand.salience

    # Dynamic programming
    for t in range(1, n_frames):
        for s, cand in enumerate(all_candidates[t]):
            best_score = -np.inf
            best_prev = -1
            for sp, prev in enumerate(all_candidates[t - 1]):
                trans_cost = _transition_cost(prev.f0_hz, cand.f0_hz, jump_penalty)
                score = scores[t - 1, sp] + cand.salience - trans_cost
                if score > best_score:
                    best_score = score
                    best_prev = sp
            scores[t, s] = best_score
            back[t, s] = best_prev

    # Backtrace
    last_state = int(np.argmax(scores[-1]))
    path_indices = np.full(n_frames, 0, dtype=np.int32)
    path_indices[-1] = last_state
    for t in range(n_frames - 1, 0, -1):
        path_indices[t - 1] = back[t, path_indices[t]]

    f0 = np.array([all_candidates[t][path_indices[t]].f0_hz for t in range(n_frames)], dtype=np.float32)
    salience = np.array([all_candidates[t][path_indices[t]].salience for t in range(n_frames)], dtype=np.float32)
    return OptimizedPath(f0_hz=f0, salience=salience, path_indices=path_indices)
