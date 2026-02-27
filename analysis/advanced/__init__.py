"""Advanced analysis features."""

from analysis.advanced.formants import (
    FormantFrame,
    FormantTrack,
    estimate_formants_from_audio,
    estimate_formants_from_spectrum,
    track_to_frames,
)
from analysis.advanced.vibrato import VibratoFeatures, detect_vibrato
from analysis.advanced.phrase_segmentation import (
    PhraseBoundary,
    PhraseSegmentationResult,
    compute_energy_envelope,
    segment_phrases_from_audio,
    segment_phrases_from_energy,
)

__all__ = [
    "FormantFrame",
    "FormantTrack",
    "estimate_formants_from_audio",
    "estimate_formants_from_spectrum",
    "track_to_frames",
    "VibratoFeatures",
    "detect_vibrato",
    "PhraseBoundary",
    "PhraseSegmentationResult",
    "compute_energy_envelope",
    "segment_phrases_from_audio",
    "segment_phrases_from_energy",
]
