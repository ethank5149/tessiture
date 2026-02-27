"""Chord detection package."""

from analysis.chords.detector import (
    ChordDetectionResult,
    compute_pitch_class_probabilities,
    detect_chord,
    propagate_chord_probabilities,
    score_chords,
)
from analysis.chords.key_detector import (
    KeyDetectionResult,
    detect_key,
    entropy_confidence,
    propagate_key_probabilities,
    score_keys,
)
from analysis.chords.key_smoother import smooth_key_probabilities, viterbi_smooth as smooth_keys_viterbi
from analysis.chords.pitch_class_histogram import (
    Observation as KeyObservation,
    build_pitch_class_histogram,
    normalize_histogram,
)
from analysis.chords.temporal_smoother import smooth_probability_sequence, viterbi_smooth
from analysis.chords.tonal_profiles import (
    KRUMHANSL_MAJOR,
    KRUMHANSL_MINOR,
    NOTE_NAMES,
    build_tonal_profile_map,
    iter_key_labels,
    rotate_profile,
)
from analysis.chords.templates import (
    CHORD_TEMPLATES,
    ChordTemplate,
    format_chord_name,
    iter_templates,
    list_templates,
)

__all__ = [
    "CHORD_TEMPLATES",
    "ChordDetectionResult",
    "ChordTemplate",
    "KRUMHANSL_MAJOR",
    "KRUMHANSL_MINOR",
    "KeyDetectionResult",
    "KeyObservation",
    "NOTE_NAMES",
    "build_pitch_class_histogram",
    "build_tonal_profile_map",
    "compute_pitch_class_probabilities",
    "detect_chord",
    "detect_key",
    "entropy_confidence",
    "format_chord_name",
    "iter_key_labels",
    "iter_templates",
    "list_templates",
    "normalize_histogram",
    "propagate_chord_probabilities",
    "propagate_key_probabilities",
    "rotate_profile",
    "score_chords",
    "score_keys",
    "smooth_key_probabilities",
    "smooth_keys_viterbi",
    "smooth_probability_sequence",
    "viterbi_smooth",
]
