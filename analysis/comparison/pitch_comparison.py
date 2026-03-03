"""Frame-by-frame pitch comparison metrics between a vocalist and a reference track."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# Threshold (cents) used to count a frame as "in-tune".
_ACCURACY_THRESHOLD_CENTS: float = 50.0


@dataclass(frozen=True)
class PitchComparisonResult:
    """Frame-by-frame pitch comparison metrics.

    Fields
    ------
    frame_deviations_cents
        Signed deviation in cents for each aligned frame pair where both
        user and reference carry a valid (voiced) pitch.
        Positive ⇒ user is sharp; negative ⇒ user is flat.
    frame_times_s
        Time stamps (seconds) of the frames included in
        *frame_deviations_cents*.
    mean_absolute_pitch_error_cents
        Mean |deviation| across all voiced paired frames.
    pitch_accuracy_ratio
        Fraction of voiced paired frames where the absolute deviation is
        within ±:data:`_ACCURACY_THRESHOLD_CENTS` cents.
    pitch_bias_cents
        Mean signed deviation (positive → user consistently sharp).
    pitch_stability_cents
        Standard deviation of the signed deviations.
    voiced_frame_count
        Number of frames where both user and reference are voiced.
    """

    frame_deviations_cents: List[float]
    frame_times_s: List[float]
    mean_absolute_pitch_error_cents: float
    pitch_accuracy_ratio: float
    pitch_bias_cents: float
    pitch_stability_cents: float
    voiced_frame_count: int


def compare_pitch_tracks(
    aligned_pairs: List[Dict],
) -> PitchComparisonResult:
    """Compute pitch comparison metrics from aligned user/reference frame pairs.

    Args:
        aligned_pairs: Output of :func:`analysis.comparison.alignment.align_to_reference`.
            Each element is a dict with ``user``, ``reference``, and ``time_s`` keys.

    Returns:
        A :class:`PitchComparisonResult` with aggregate and per-frame metrics.
    """
    deviations: List[float] = []
    times: List[float] = []

    for pair in aligned_pairs:
        user_frame = pair.get("user") or {}
        ref_frame = pair.get("reference")
        time_s = float(pair.get("time_s", 0.0))

        if ref_frame is None:
            continue

        user_f0 = float(user_frame.get("f0_hz") or user_frame.get("f0") or 0.0)
        ref_f0 = float(ref_frame.get("f0_hz") or ref_frame.get("f0") or 0.0)

        if user_f0 <= 0.0 or ref_f0 <= 0.0:
            continue

        # cents = 1200 * log2(user / reference)
        try:
            deviation = 1200.0 * math.log2(user_f0 / ref_f0)
        except (ValueError, ZeroDivisionError):
            continue

        if not math.isfinite(deviation):
            continue

        deviations.append(deviation)
        times.append(time_s)

    voiced_frame_count = len(deviations)

    if voiced_frame_count == 0:
        logger.debug("pitch_comparison.no_voiced_pairs")
        return PitchComparisonResult(
            frame_deviations_cents=[],
            frame_times_s=[],
            mean_absolute_pitch_error_cents=0.0,
            pitch_accuracy_ratio=0.0,
            pitch_bias_cents=0.0,
            pitch_stability_cents=0.0,
            voiced_frame_count=0,
        )

    arr = np.asarray(deviations, dtype=float)
    mean_abs_error = float(np.mean(np.abs(arr)))
    accuracy_ratio = float(np.mean(np.abs(arr) <= _ACCURACY_THRESHOLD_CENTS))
    pitch_bias = float(np.mean(arr))
    pitch_stability = float(np.std(arr))

    logger.debug(
        "pitch_comparison.result voiced_frames=%d mape_cents=%.2f accuracy=%.3f bias=%.2f stability=%.2f",
        voiced_frame_count,
        mean_abs_error,
        accuracy_ratio,
        pitch_bias,
        pitch_stability,
    )

    return PitchComparisonResult(
        frame_deviations_cents=deviations,
        frame_times_s=times,
        mean_absolute_pitch_error_cents=mean_abs_error,
        pitch_accuracy_ratio=accuracy_ratio,
        pitch_bias_cents=pitch_bias,
        pitch_stability_cents=pitch_stability,
        voiced_frame_count=voiced_frame_count,
    )
