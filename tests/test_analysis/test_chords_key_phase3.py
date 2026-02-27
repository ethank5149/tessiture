import numpy as np

from analysis.chords.detector import (
    compute_pitch_class_probabilities,
    detect_chord,
    propagate_chord_probabilities,
)
from analysis.chords.key_detector import detect_key, entropy_confidence


def test_detect_chord_finds_c_major_from_midi_notes() -> None:
    result = detect_chord([60.0, 64.0, 67.0], input_unit="midi", max_notes=4)

    assert result.best_chord is not None
    assert result.best_chord.startswith("C:")
    assert result.probabilities


def test_propagate_chord_probabilities_normalizes_distribution() -> None:
    probs = propagate_chord_probabilities(
        [60.0, 64.0, 67.0],
        probabilities=[0.8, 0.9, 0.85],
        input_unit="midi",
    )

    total = float(sum(probs.values()))
    assert probs
    assert abs(total - 1.0) < 1e-6


def test_compute_pitch_class_probabilities_from_hz_notes() -> None:
    histogram = compute_pitch_class_probabilities(
        [261.63, 329.63, 392.0],
        input_unit="hz",
    )

    assert histogram.shape == (12,)
    assert np.isclose(np.sum(histogram), 1.0)


def test_detect_key_identifies_c_major_profile() -> None:
    # C major scale tones in MIDI
    notes = [60, 62, 64, 65, 67, 69, 71, 72]
    result = detect_key(notes, input_unit="midi")

    assert result.best_key is not None
    assert result.best_key.startswith("C:")
    assert result.confidence >= 0.0


def test_entropy_confidence_monotonic_behavior() -> None:
    peaky = entropy_confidence([0.95, 0.03, 0.02])
    flat = entropy_confidence([1 / 3, 1 / 3, 1 / 3])

    assert peaky > flat
