"""Key detection utilities using Krumhansl-Schmuckler tonal profiles."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from analysis.chords.pitch_class_histogram import Observation, build_pitch_class_histogram
from analysis.chords.tonal_profiles import build_tonal_profile_map, iter_key_labels


_PITCH_CLASS_BY_NOTE = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

_CHORD_ROOT_PATTERN = re.compile(r"^\s*([A-Ga-g])([#b♯♭]*)")


def _parse_pitch_class_observation(observation: Any) -> Optional[float]:
    if isinstance(observation, (int, float, np.integer, np.floating)):
        value = float(observation)
        if np.isfinite(value):
            return float(int(round(value)) % 12)
        return None

    if not isinstance(observation, str):
        return None

    token = observation.strip()
    if not token:
        return None

    try:
        numeric_value = float(token)
    except (TypeError, ValueError):
        numeric_value = None
    if numeric_value is not None and np.isfinite(numeric_value):
        return float(int(round(numeric_value)) % 12)

    match = _CHORD_ROOT_PATTERN.match(token)
    if not match:
        return None

    pitch_class = _PITCH_CLASS_BY_NOTE[match.group(1).upper()]
    for accidental in match.group(2):
        if accidental in {"#", "♯"}:
            pitch_class += 1
        elif accidental in {"b", "♭"}:
            pitch_class -= 1

    return float(pitch_class % 12)


@dataclass(frozen=True)
class KeyDetectionResult:
    best_key: Optional[str]
    probabilities: Dict[str, float]
    confidence: float
    alternatives: List[Tuple[str, float]]


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("histogram and profile must have the same shape")
    a_centered = a - np.mean(a)
    b_centered = b - np.mean(b)
    denom = float(np.linalg.norm(a_centered) * np.linalg.norm(b_centered))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(a_centered, b_centered) / denom)


def _softmax(scores: np.ndarray, beta: float = 1.0) -> np.ndarray:
    if scores.size == 0:
        return scores
    scaled = scores * float(beta)
    scaled = scaled - np.max(scaled)
    exp_vals = np.exp(scaled)
    return exp_vals / np.sum(exp_vals)


def _confidence_from_ranked(ranked: List[Tuple[str, float]]) -> float:
    if not ranked:
        return 0.0
    if len(ranked) == 1:
        return float(ranked[0][1])
    return float(ranked[0][1] - ranked[1][1])


def entropy_confidence(probabilities: Sequence[float]) -> float:
    """Compute normalized entropy confidence for key probabilities."""
    probs = np.asarray(probabilities, dtype=np.float64)
    if probs.size == 0:
        return 0.0
    probs = np.clip(probs, 1e-12, 1.0)
    probs = probs / float(np.sum(probs))
    entropy = -float(np.sum(probs * np.log(probs)))
    max_entropy = float(np.log(probs.size)) if probs.size > 0 else 0.0
    if max_entropy <= 0.0:
        return 0.0
    return float(1.0 - entropy / max_entropy)


def score_keys(
    observations: Sequence[Observation],
    *,
    weights: Optional[Sequence[float]] = None,
    input_unit: str = "midi",
    softmax_beta: float = 1.0,
    profile_map: Optional[Dict[str, np.ndarray]] = None,
) -> Tuple[List[str], np.ndarray]:
    """Score candidate keys for a set of pitch-class observations.

    Args:
        observations: Sequence of MIDI notes, pitch classes, or (note, weight) pairs.
        weights: Optional weights aligned with observations.
        input_unit: "midi" or "pc" for pitch classes.
        softmax_beta: Inverse temperature for softmax probability conversion.
        profile_map: Optional mapping of key label to tonal profile.

    Returns:
        Tuple of (key_labels, probabilities).
    """
    histogram = build_pitch_class_histogram(
        observations,
        weights=weights,
        input_unit=input_unit,
        normalize=True,
    )

    if profile_map is None:
        profile_map = build_tonal_profile_map()

    key_labels = [label for label in iter_key_labels() if label in profile_map]
    if not key_labels:
        key_labels = list(profile_map.keys())

    scores = np.array([
        _correlation(histogram, profile_map[label]) for label in key_labels
    ], dtype=np.float64)
    probabilities = _softmax(scores, beta=softmax_beta)
    return key_labels, probabilities


def propagate_key_probabilities(
    chord_probabilities: Dict[str, float],
    *,
    profile_map: Optional[Dict[str, np.ndarray]] = None,
) -> Tuple[Dict[str, float], float]:
    """Propagate chord probabilities into key probabilities.

    Uses pitch-class histograms to compute P(K) and returns entropy confidence.
    """
    if not chord_probabilities:
        return {}, 0.0

    observations: List[float] = []
    weights: List[float] = []
    for chord_name, raw_weight in chord_probabilities.items():
        weight = float(raw_weight)
        if not np.isfinite(weight) or weight <= 0.0:
            continue
        pitch_class = _parse_pitch_class_observation(chord_name)
        if pitch_class is None:
            continue
        observations.append(pitch_class)
        weights.append(weight)

    if observations:
        histogram = build_pitch_class_histogram(
            observations,
            weights=weights,
            input_unit="pc",
            normalize=True,
        )
    else:
        histogram = np.zeros(12, dtype=np.float64)

    if profile_map is None:
        profile_map = build_tonal_profile_map()

    key_labels = [label for label in iter_key_labels() if label in profile_map]
    if not key_labels:
        key_labels = list(profile_map.keys())

    scores = np.array([
        _correlation(histogram, profile_map[label]) for label in key_labels
    ], dtype=np.float64)
    probabilities = _softmax(scores, beta=1.0)
    prob_map = {label: float(prob) for label, prob in zip(key_labels, probabilities)}
    confidence = entropy_confidence(probabilities)
    return prob_map, confidence


def detect_key(
    observations: Sequence[Observation],
    *,
    weights: Optional[Sequence[float]] = None,
    input_unit: str = "midi",
    softmax_beta: float = 1.0,
    profile_map: Optional[Dict[str, np.ndarray]] = None,
    top_k: int = 5,
) -> KeyDetectionResult:
    """Detect the most likely key for a set of observations."""
    key_labels, probabilities = score_keys(
        observations,
        weights=weights,
        input_unit=input_unit,
        softmax_beta=softmax_beta,
        profile_map=profile_map,
    )
    if not key_labels:
        return KeyDetectionResult(best_key=None, probabilities={}, confidence=0.0, alternatives=[])

    prob_map = {label: float(prob) for label, prob in zip(key_labels, probabilities)}
    ranked = sorted(prob_map.items(), key=lambda item: item[1], reverse=True)
    best = ranked[0][0] if ranked else None
    confidence = entropy_confidence(list(probabilities))
    alternatives = ranked[1 : max(top_k, 1)] if ranked else []
    return KeyDetectionResult(
        best_key=best,
        probabilities=prob_map,
        confidence=confidence,
        alternatives=alternatives,
    )


@dataclass(frozen=True)
class KeyTrajectoryEntry:
    """A single entry in a windowed key trajectory."""
    start_s: float
    end_s: float
    label: str
    confidence: float
    probabilities: Dict[str, float]


def detect_key_trajectory(
    observations: Sequence[float],
    timestamps_s: Sequence[float],
    *,
    input_unit: str = "midi",
    window_s: float = 8.0,
    hop_s: float = 4.0,
    softmax_beta: float = 1.0,
    transition_penalty: float = 2.0,
    profile_map: Optional[Dict[str, np.ndarray]] = None,
) -> List[KeyTrajectoryEntry]:
    """Detect a key trajectory using overlapping windows + Viterbi smoothing.

    Slides a window across the observation sequence, computes per-window key
    probabilities using Krumhansl-Schmuckler correlation, then smooths the
    resulting label sequence with Viterbi dynamic programming to penalize
    implausible rapid modulations.

    Args:
        observations: MIDI note values (or pitch classes if input_unit="pc").
        timestamps_s: Timestamp in seconds for each observation.
        input_unit: "midi" or "pc".
        window_s: Window duration in seconds.
        hop_s: Hop between window centres in seconds.
        softmax_beta: Inverse temperature for probability conversion.
        transition_penalty: Log-domain penalty for key changes in Viterbi.
        profile_map: Optional tonal profile map.

    Returns:
        List of KeyTrajectoryEntry with one entry per smoothed window.
    """
    from analysis.chords._viterbi_shared import _viterbi_smooth_sequences

    if len(observations) == 0 or len(timestamps_s) == 0:
        return []

    obs_arr = np.asarray(observations, dtype=float)
    time_arr = np.asarray(timestamps_s, dtype=float)

    if profile_map is None:
        profile_map = build_tonal_profile_map()

    key_labels = [label for label in iter_key_labels() if label in profile_map]
    if not key_labels:
        key_labels = list(profile_map.keys())

    duration = float(np.max(time_arr) - np.min(time_arr))
    if duration <= 0.0 or len(key_labels) == 0:
        # Fall back to global detection
        result = detect_key(observations, input_unit=input_unit,
                            softmax_beta=softmax_beta, profile_map=profile_map)
        if result.best_key is None:
            return []
        return [KeyTrajectoryEntry(
            start_s=float(np.min(time_arr)),
            end_s=float(np.max(time_arr)),
            label=result.best_key,
            confidence=result.confidence,
            probabilities=result.probabilities,
        )]

    t_start = float(np.min(time_arr))
    t_end = float(np.max(time_arr))

    # Build windows
    window_centres: List[float] = []
    c = t_start + window_s / 2.0
    while c - window_s / 2.0 < t_end:
        window_centres.append(c)
        c += hop_s

    if not window_centres:
        window_centres = [(t_start + t_end) / 2.0]

    # Compute per-window key probability frames
    prob_frames: List[np.ndarray] = []
    window_spans: List[Tuple[float, float]] = []

    for centre in window_centres:
        w_start = centre - window_s / 2.0
        w_end = centre + window_s / 2.0
        mask = (time_arr >= w_start) & (time_arr < w_end)
        window_obs = obs_arr[mask]

        if len(window_obs) < 2:
            # Not enough observations — uniform distribution
            prob_frames.append(np.ones(len(key_labels), dtype=float) / len(key_labels))
        else:
            _, probs = score_keys(
                list(window_obs),
                input_unit=input_unit,
                softmax_beta=softmax_beta,
                profile_map=profile_map,
            )
            prob_frames.append(probs)

        window_spans.append((max(w_start, t_start), min(w_end, t_end)))

    # Stack into (T, N) probability matrix and run Viterbi smoothing
    prob_matrix = np.array(prob_frames, dtype=np.float64)
    smoothed_labels = _viterbi_smooth_sequences(
        key_labels, prob_matrix, transition_penalty=transition_penalty
    )

    # Build trajectory, merging adjacent windows with the same key
    trajectory: List[KeyTrajectoryEntry] = []
    for idx, label in enumerate(smoothed_labels):
        span_start, span_end = window_spans[idx]
        window_probs = {k: float(v) for k, v in zip(key_labels, prob_frames[idx])}
        conf = entropy_confidence(list(prob_frames[idx]))

        if trajectory and trajectory[-1].label == label:
            # Merge with previous entry
            prev = trajectory[-1]
            merged_probs = {k: max(prev.probabilities.get(k, 0.0), window_probs.get(k, 0.0))
                           for k in key_labels}
            trajectory[-1] = KeyTrajectoryEntry(
                start_s=prev.start_s,
                end_s=span_end,
                label=label,
                confidence=max(prev.confidence, conf),
                probabilities=merged_probs,
            )
        else:
            trajectory.append(KeyTrajectoryEntry(
                start_s=span_start,
                end_s=span_end,
                label=label,
                confidence=conf,
                probabilities=window_probs,
            ))

    return trajectory


__all__ = [
    "KeyDetectionResult",
    "KeyTrajectoryEntry",
    "detect_key",
    "detect_key_trajectory",
    "entropy_confidence",
    "propagate_key_probabilities",
    "score_keys",
]