"""Parameter ranges for calibration reference generation."""

from __future__ import annotations

from typing import Dict, Tuple

ParameterRange = Tuple[float, float]
ParameterRanges = Dict[str, ParameterRange]


def get_default_parameter_ranges() -> ParameterRanges:
    """Return default parameter ranges for calibration reference generation.

    Ranges reflect Phase 1.1 requirements and are expressed as inclusive
    min/max values.
    """

    return {
        "f0_hz": (82.0, 2093.0),
        "detune_cents": (-50.0, 50.0),
        "amplitude_dbfs": (-20.0, 0.0),
        "harmonic_ratio": (0.1, 1.0),
        "note_count": (1.0, 4.0),
        "duration_s": (0.05, 3.0),
        "snr_db": (20.0, 60.0),
        "vibrato_depth_cents": (-20.0, 20.0),
        "vibrato_rate_hz": (3.0, 8.0),
    }
