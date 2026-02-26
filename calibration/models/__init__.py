"""Model fitting utilities for calibration."""

from .confidence_models import build_confidence_surface, suggest_detection_thresholds
from .pitch_calibration import fit_pitch_bias, fit_pitch_variance

__all__ = [
    "build_confidence_surface",
    "suggest_detection_thresholds",
    "fit_pitch_bias",
    "fit_pitch_variance",
]
