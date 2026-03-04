"""Chord detection utilities for dyads/triads/tetrads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from analysis.chords.templates import (
    ChordTemplate,
    format_chord_name,
    iter_templates,
)


@dataclass(frozen=True)
class ChordDetectionResult:
    best_chord: Optional[str]
    probabilities: Dict[str, float]
    alternatives: List[Tuple[str, float]]


def _frequency_to_midi(frequency_hz: float) -> float:
    if frequency_hz <= 0.0:
        return 0.0
    return float(69.0 + 12.0 * np.log2(frequency_hz / 440.0))


def _normalize_notes(
    notes: Sequence[float],
    *,
    input_unit: str,
) -> List[float]:
    if input_unit not in {"midi", "hz"}:
        raise ValueError("input_unit must be 'midi' or 'hz'")
    if input_unit == "hz":
        return [_frequency_to_midi(float(n)) for n in notes if float(n) > 0.0]
    return [float(n) for n in notes]


def _unique_pitch_classes(midi_notes: Sequence[float], max_notes: int = 4) -> List[int]:
    if not midi_notes:
        return []
    rounded = sorted({int(round(note)) % 12 for note in midi_notes})
    return rounded[:max_notes]


def _iter_note_probabilities(
    notes: Sequence[float],
    probabilities: Optional[Sequence[float]],
    *,
    input_unit: str,
) -> Iterable[Tuple[float, float]]:
    if input_unit not in {"midi", "hz"}:
        raise ValueError("input_unit must be 'midi' or 'hz'")
    if probabilities is not None and len(probabilities) != len(notes):
        raise ValueError("probabilities must match notes length")
    for idx, note in enumerate(notes):
        weight = 1.0 if probabilities is None else float(probabilities[idx])
        if not np.isfinite(weight) or weight <= 0.0:
            continue
        value = float(note)
        if input_unit == "hz":
            if value <= 0.0:
                continue
            value = _frequency_to_midi(value)
        if not np.isfinite(value):
            continue
        yield value, weight


def compute_pitch_class_probabilities(
    notes: Sequence[float],
    *,
    probabilities: Optional[Sequence[float]] = None,
    input_unit: str = "midi",
) -> np.ndarray:
    """Compute pitch-class probability distribution from note probabilities."""
    histogram = np.zeros(12, dtype=np.float64)
    total_weight = 0.0
    for midi_note, weight in _iter_note_probabilities(
        notes, probabilities, input_unit=input_unit
    ):
        pitch_class = int(round(midi_note)) % 12
        histogram[pitch_class] += float(weight)
        total_weight += float(weight)
    if total_weight > 0.0:
        histogram /= total_weight
    return histogram


def _score_template(
    pitch_classes: Sequence[int],
    root_pc: int,
    template: ChordTemplate,
    *,
    sigma: float,
) -> float:
    if not pitch_classes:
        return -np.inf
    target_intervals = set(template.intervals)
    expected = {((root_pc + interval) % 12) for interval in target_intervals}
    observed = set(pitch_classes)

    missing = expected - observed
    extra = observed - expected

    error_sum = 0.0
    for pc in missing:
        distances = [min((pc - exp) % 12, (exp - pc) % 12) for exp in observed] or [12]
        error_sum += float(min(distances) ** 2)
    for pc in extra:
        distances = [min((pc - exp) % 12, (exp - pc) % 12) for exp in expected] or [12]
        error_sum += float(min(distances) ** 2)

    # error_sum combines squared PC distances (semitone²) and a count-based cardinality
    # penalty (0.5 per missing/extra note). sigma simultaneously controls both components.
    # This is an intentional design choice: the penalty grows with both distance and count.
    base_penalty = float((len(missing) + len(extra)) * 0.5)
    error_sum += base_penalty
    sigma = max(sigma, 1e-6)
    return float(-error_sum / (2.0 * sigma**2))


def _softmax(scores: np.ndarray, beta: float = 1.0) -> np.ndarray:
    if scores.size == 0:
        return scores
    scaled = scores * float(beta)
    scaled = scaled - np.max(scaled)
    exp_vals = np.exp(scaled)
    return exp_vals / np.sum(exp_vals)


def score_chords(
    notes: Sequence[float],
    *,
    input_unit: str = "midi",
    max_notes: int = 4,
    sigma: float = 1.0,
    beta: float = 1.0,
    templates: Optional[Iterable[ChordTemplate]] = None,
) -> Tuple[List[str], np.ndarray]:
    """Score chords from candidate notes.

    Args:
        notes: Candidate notes (MIDI numbers or Hz).
        input_unit: "midi" or "hz".
        max_notes: Maximum number of notes to consider.
        sigma: Distance spread for Gaussian-like scoring.
        beta: Softmax temperature inverse.
        templates: Optional chord templates to use.

    Returns:
        Tuple of (chord_names, probabilities).
    """
    midi_notes = _normalize_notes(notes, input_unit=input_unit)
    pitch_classes = _unique_pitch_classes(midi_notes, max_notes=max_notes)
    if templates is None:
        templates = iter_templates(max_notes=max_notes)

    chord_names: List[str] = []
    scores: List[float] = []

    for template in templates:
        for root_pc in range(12):
            name = format_chord_name(root_pc, template.quality)
            score = _score_template(pitch_classes, root_pc, template, sigma=sigma)
            chord_names.append(name)
            scores.append(score)

    score_array = np.array(scores, dtype=np.float64)
    probabilities = _softmax(score_array, beta=beta)
    return chord_names, probabilities


def propagate_chord_probabilities(
    notes: Sequence[float],
    *,
    probabilities: Optional[Sequence[float]] = None,
    input_unit: str = "midi",
    max_notes: int = 4,
    templates: Optional[Iterable[ChordTemplate]] = None,
) -> Dict[str, float]:
    """Propagate note probabilities into chord probabilities.

    Implements P(C_i) = Σ_j P(C_i | N_j) * P(N_j) using pitch-class membership.
    """
    pc_probs = compute_pitch_class_probabilities(
        notes, probabilities=probabilities, input_unit=input_unit
    )
    if templates is None:
        templates = iter_templates(max_notes=max_notes)

    chord_probs: Dict[str, float] = {}
    for template in templates:
        intervals = template.intervals
        denom = float(len(intervals)) if intervals else 1.0
        for root_pc in range(12):
            chord_pcs = [(root_pc + interval) % 12 for interval in intervals]
            likelihood = float(np.sum(pc_probs[chord_pcs]) / denom)
            name = format_chord_name(root_pc, template.quality)
            chord_probs[name] = likelihood

    total = float(np.sum(list(chord_probs.values())))
    if total > 0.0:
        chord_probs = {name: float(prob / total) for name, prob in chord_probs.items()}
    return chord_probs


def detect_chord(
    notes: Sequence[float],
    *,
    input_unit: str = "midi",
    max_notes: int = 4,
    sigma: float = 1.0,
    beta: float = 1.0,
    templates: Optional[Iterable[ChordTemplate]] = None,
    top_k: int = 5,
) -> ChordDetectionResult:
    """Detect the best matching chord for candidate notes."""
    chord_names, probabilities = score_chords(
        notes,
        input_unit=input_unit,
        max_notes=max_notes,
        sigma=sigma,
        beta=beta,
        templates=templates,
    )
    if not chord_names:
        return ChordDetectionResult(best_chord=None, probabilities={}, alternatives=[])

    prob_map = {name: float(prob) for name, prob in zip(chord_names, probabilities)}
    ranked = sorted(prob_map.items(), key=lambda item: item[1], reverse=True)
    best = ranked[0][0] if ranked else None
    alternatives = ranked[1 : max(top_k, 1)] if ranked else []
    return ChordDetectionResult(best_chord=best, probabilities=prob_map, alternatives=alternatives)


__all__ = [
    "ChordDetectionResult",
    "compute_pitch_class_probabilities",
    "detect_chord",
    "propagate_chord_probabilities",
    "score_chords",
]
