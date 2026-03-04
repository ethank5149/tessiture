"""Vocal range and tessitura comparison metrics."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RangeComparisonResult:
    """Vocal range comparison metrics.

    Fields
    ------
    user_range_min_midi, user_range_max_midi
        Observed MIDI range of the user's voiced frames.  ``None`` if no
        voiced frames were provided.
    reference_range_min_midi, reference_range_max_midi
        MIDI range implied by the reference note events.  ``None`` if no
        reference events were provided.
    range_overlap_semitones
        Size of the intersection [user_min, user_max] ∩ [ref_min, ref_max]
        in semitones.  0 when there is no overlap or either range is ``None``.
    range_coverage_ratio
        overlap / reference_range_span.  0 when the reference range is zero
        or unavailable.
    tessitura_center_offset_semitones
        user_center − ref_center (semitones).  ``None`` when either tessitura
        center is unavailable.
    out_of_range_note_fraction
        Fraction of reference notes whose MIDI pitch falls outside the user's
        observed MIDI range.  0 when either set is empty.
    strain_zone_incursion_ratio
        Fraction of user voiced-MIDI values that fall inside any detected
        strain zones from the tessitura analysis payload.  0 when no strain
        zones are available.
    """

    user_range_min_midi: Optional[float]
    user_range_max_midi: Optional[float]
    reference_range_min_midi: Optional[float]
    reference_range_max_midi: Optional[float]
    range_overlap_semitones: float
    range_coverage_ratio: float
    tessitura_center_offset_semitones: Optional[float]
    out_of_range_note_fraction: float
    strain_zone_incursion_ratio: float


def compare_vocal_ranges(
    user_voiced_midi: List[float],
    reference_note_events: List[Dict],
    user_tessitura_metrics: Optional[Dict] = None,
) -> RangeComparisonResult:
    """Compare user vocal range against reference note events and tessitura metrics.

    Args:
        user_voiced_midi: All voiced MIDI values from the user's pitch track.
        reference_note_events: Reference note events dicts with ``midi``
            (or ``pitch``) and optionally ``start_s``/``end_s``.
        user_tessitura_metrics: Dict from ``analysis["tessitura"]["metrics"]``
            in the pipeline output.  Used for strain-zone and comfort-center
            data.  May be ``None``.

    Returns:
        :class:`RangeComparisonResult` with aggregate range metrics.
    """
    # --- user range ---
    user_range_min: Optional[float] = None
    user_range_max: Optional[float] = None
    if user_voiced_midi:
        arr = np.asarray([float(m) for m in user_voiced_midi if m is not None], dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size:
            user_range_min = float(np.min(arr))
            user_range_max = float(np.max(arr))

    # --- reference range ---
    ref_midi_values: List[float] = []
    for ev in reference_note_events:
        midi = ev.get("midi") or ev.get("pitch")
        if midi is not None:
            ref_midi_values.append(float(midi))

    reference_range_min: Optional[float] = None
    reference_range_max: Optional[float] = None
    if ref_midi_values:
        reference_range_min = float(min(ref_midi_values))
        reference_range_max = float(max(ref_midi_values))

    # --- range overlap ---
    range_overlap_semitones = 0.0
    range_coverage_ratio = 0.0
    if (
        user_range_min is not None
        and user_range_max is not None
        and reference_range_min is not None
        and reference_range_max is not None
    ):
        overlap_low = max(user_range_min, reference_range_min)
        overlap_high = min(user_range_max, reference_range_max)
        range_overlap_semitones = max(overlap_high - overlap_low, 0.0)
        ref_span = reference_range_max - reference_range_min
        if ref_span > 0.0:
            range_coverage_ratio = min(range_overlap_semitones / ref_span, 1.0)

    # --- tessitura center offset ---
    tessitura_center_offset: Optional[float] = None
    user_comfort_center: Optional[float] = None
    ref_comfort_center: Optional[float] = None

    if isinstance(user_tessitura_metrics, dict):
        cc = user_tessitura_metrics.get("comfort_center")
        if cc is not None:
            user_comfort_center = float(cc)

    # Reference tessitura center: use weighted mean of MIDI values if available,
    # as the range midpoint over-estimates center for non-uniform pitch distributions.
    if ref_midi_values:
        ref_comfort_center = float(np.mean(ref_midi_values))
    elif reference_range_min is not None and reference_range_max is not None:
        ref_comfort_center = (reference_range_min + reference_range_max) / 2.0
    else:
        ref_comfort_center = None

    if user_comfort_center is not None and ref_comfort_center is not None:
        tessitura_center_offset = user_comfort_center - ref_comfort_center

    # --- out-of-range note fraction ---
    out_of_range_note_fraction = 0.0
    if ref_midi_values and user_range_min is not None and user_range_max is not None:
        out_of_range = sum(
            1 for m in ref_midi_values if m < user_range_min or m > user_range_max
        )
        out_of_range_note_fraction = float(out_of_range) / float(len(ref_midi_values))

    # --- strain zone incursion ratio ---
    strain_zone_incursion_ratio = 0.0
    if user_voiced_midi and isinstance(user_tessitura_metrics, dict):
        strain_zones = user_tessitura_metrics.get("strain_zones") or []
        if strain_zones:
            user_arr = np.asarray([float(m) for m in user_voiced_midi if m is not None], dtype=float)
            user_arr = user_arr[np.isfinite(user_arr)]
            if user_arr.size:
                in_strain = np.zeros(user_arr.size, dtype=bool)
                for zone in strain_zones:
                    low = zone.get("low") if isinstance(zone, dict) else getattr(zone, "low", None)
                    high = zone.get("high") if isinstance(zone, dict) else getattr(zone, "high", None)
                    if low is None or high is None:
                        continue
                    in_strain |= (user_arr >= float(low)) & (user_arr <= float(high))
                strain_zone_incursion_ratio = float(np.mean(in_strain))

    logger.debug(
        "range_comparison.result user_range=[%.1f, %.1f] ref_range=[%.1f, %.1f] overlap=%.2f coverage=%.3f",
        user_range_min if user_range_min is not None else float("nan"),
        user_range_max if user_range_max is not None else float("nan"),
        reference_range_min if reference_range_min is not None else float("nan"),
        reference_range_max if reference_range_max is not None else float("nan"),
        range_overlap_semitones,
        range_coverage_ratio,
    )

    return RangeComparisonResult(
        user_range_min_midi=user_range_min,
        user_range_max_midi=user_range_max,
        reference_range_min_midi=reference_range_min,
        reference_range_max_midi=reference_range_max,
        range_overlap_semitones=range_overlap_semitones,
        range_coverage_ratio=range_coverage_ratio,
        tessitura_center_offset_semitones=tessitura_center_offset,
        out_of_range_note_fraction=out_of_range_note_fraction,
        strain_zone_incursion_ratio=strain_zone_incursion_ratio,
    )
