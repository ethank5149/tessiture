"""Formant (F1/F2) comparison metrics between a vocalist and a reference track."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FormantComparisonResult:
    """Formant comparison metrics.

    Fields
    ------
    mean_f1_deviation_hz
        Mean absolute difference between user and reference F1 formant
        (Hz).  ``None`` if either formant summary is unavailable.
    mean_f2_deviation_hz
        Mean absolute difference between user and reference F2 formant
        (Hz).  ``None`` if either formant summary is unavailable.
    spectral_centroid_deviation_hz
        Difference in average spectral brightness estimate derived from
        the mean F1/F2 midpoint.  ``None`` if formant data is unavailable.
    formant_data_available
        ``True`` when both *user_formant_summary* and
        *reference_formant_summary* carried valid ``mean_f1_hz`` and
        ``mean_f2_hz`` fields; otherwise ``False``.
    """

    mean_f1_deviation_hz: Optional[float]
    mean_f2_deviation_hz: Optional[float]
    spectral_centroid_deviation_hz: Optional[float]
    formant_data_available: bool


def compare_formants(
    user_formant_summary: Optional[Dict],
    reference_formant_summary: Optional[Dict],
) -> FormantComparisonResult:
    """Compute formant comparison metrics from per-track formant summaries.

    Both inputs must be dicts with valid ``mean_f1_hz`` and ``mean_f2_hz``
    numeric fields to produce deviation metrics.  Either or both being
    ``None``, or missing / non-numeric values, results in
    ``formant_data_available=False`` with all deviations set to ``None``.

    Args:
        user_formant_summary: Dict from ``analysis["advanced"]["formants"]``
            of the user pipeline output.  Expected keys: ``mean_f1_hz``,
            ``mean_f2_hz``.
        reference_formant_summary: Same schema from the reference pipeline
            output (or from :attr:`ReferenceAnalysis.formant_summary`).

    Returns:
        :class:`FormantComparisonResult` with deviation fields.
    """
    user_f1 = _extract_hz(user_formant_summary, "mean_f1_hz") or _extract_hz(user_formant_summary, "f1_hz_mean")
    user_f2 = _extract_hz(user_formant_summary, "mean_f2_hz") or _extract_hz(user_formant_summary, "f2_hz_mean")
    ref_f1 = _extract_hz(reference_formant_summary, "mean_f1_hz") or _extract_hz(reference_formant_summary, "f1_hz_mean")
    ref_f2 = _extract_hz(reference_formant_summary, "mean_f2_hz") or _extract_hz(reference_formant_summary, "f2_hz_mean")

    if None in (user_f1, user_f2, ref_f1, ref_f2):
        logger.debug(
            "formant_comparison.data_unavailable user_f1=%s user_f2=%s ref_f1=%s ref_f2=%s",
            user_f1,
            user_f2,
            ref_f1,
            ref_f2,
        )
        return FormantComparisonResult(
            mean_f1_deviation_hz=None,
            mean_f2_deviation_hz=None,
            spectral_centroid_deviation_hz=None,
            formant_data_available=False,
        )

    # All four values are valid floats.
    mean_f1_deviation = abs(user_f1 - ref_f1)  # type: ignore[operator]
    mean_f2_deviation = abs(user_f2 - ref_f2)  # type: ignore[operator]

    # Spectral brightness estimate: midpoint of F1+F2.
    user_centroid = (user_f1 + user_f2) / 2.0  # type: ignore[operator]
    ref_centroid = (ref_f1 + ref_f2) / 2.0  # type: ignore[operator]
    spectral_centroid_deviation = user_centroid - ref_centroid  # signed

    logger.debug(
        "formant_comparison.result f1_dev_hz=%.1f f2_dev_hz=%.1f centroid_dev_hz=%.1f",
        mean_f1_deviation,
        mean_f2_deviation,
        spectral_centroid_deviation,
    )

    return FormantComparisonResult(
        mean_f1_deviation_hz=float(mean_f1_deviation),
        mean_f2_deviation_hz=float(mean_f2_deviation),
        spectral_centroid_deviation_hz=float(spectral_centroid_deviation),
        formant_data_available=True,
    )


def _extract_hz(summary: Optional[Dict], key: str) -> Optional[float]:
    """Extract a positive finite Hz value from *summary[key]*, or return ``None``."""
    if not isinstance(summary, dict):
        return None
    value = summary.get(key)
    if value is None:
        return None
    try:
        fval = float(value)
    except (TypeError, ValueError):
        return None
    if not (fval > 0.0 and fval < float("inf")):
        return None
    return fval
