"""Digital signal processing utilities for Tessiture analysis."""

from analysis.dsp.peak_detection import HarmonicCandidate, HarmonicFrame, Peak, detect_harmonics
from analysis.dsp.preprocessing import PreprocessResult, preprocess_audio
from analysis.dsp.stft import StftResult, compute_stft
from analysis.dsp.vocal_separation import (
    SeparationResult,
    detect_audio_type,
    is_available as vocal_separation_available,
    separate_vocals,
)

__all__ = [
    "Peak",
    "HarmonicCandidate",
    "HarmonicFrame",
    "detect_harmonics",
    "PreprocessResult",
    "preprocess_audio",
    "StftResult",
    "compute_stft",
    "SeparationResult",
    "detect_audio_type",
    "vocal_separation_available",
    "separate_vocals",
]
