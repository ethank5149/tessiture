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
    confidence = _confidence_from_ranked(ranked)
    alternatives = ranked[1 : max(top_k, 1)] if ranked else []
    return KeyDetectionResult(
        best_key=best,
        probabilities=prob_map,
        confidence=confidence,
        alternatives=alternatives,
    )


__all__ = [
    "KeyDetectionResult",
    "detect_key",
    "entropy_confidence",
    "propagate_key_probabilities",
    "score_keys",
]