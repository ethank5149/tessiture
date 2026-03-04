"""Note-timing and rhythm comparison metrics between a vocalist and a reference track."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RhythmComparisonResult:
    """Rhythm comparison metrics derived by matching user notes to reference notes.

    Fields
    ------
    onset_deviations_ms
        Signed deviation of each matched user note onset relative to the
        reference note onset (user_start − reference_start, in ms).
        Positive ⇒ user was late; negative ⇒ user was early.
    duration_ratios
        user_duration / reference_duration for each matched note pair.
        Values > 1 ⇒ user held the note longer.
    mean_onset_error_ms
        Mean absolute onset deviation across all matched notes (ms).
    rhythmic_consistency_ms
        Standard deviation of the signed onset deviations (ms).
    note_hit_rate
        Fraction of reference notes for which a matching user note was found
        within the onset and MIDI tolerances.
    matched_note_count
        Number of reference notes that were successfully matched.
    reference_note_count
        Total number of reference notes used for comparison.
    """

    onset_deviations_ms: List[float]
    duration_ratios: List[float]
    mean_onset_error_ms: float
    rhythmic_consistency_ms: float
    note_hit_rate: float
    matched_note_count: int
    reference_note_count: int


def compare_note_timing(
    user_note_events: List[Dict],
    reference_note_events: List[Dict],
    onset_tolerance_s: float = 0.15,
    midi_tolerance: float = 2.0,
) -> RhythmComparisonResult:
    """Compute rhythm comparison metrics by matching user notes to reference notes.

    Matching strategy: for each reference note, find the nearest user note
    (by start time) within *onset_tolerance_s* **and** within *midi_tolerance*
    semitones.  A reference note with no match within tolerance counts as
    missed.

    Args:
        user_note_events: List of dicts with keys ``start_s``, ``end_s``,
            ``midi``, ``note_name``, ``duration_s``.
        reference_note_events: Same schema as *user_note_events*.
        onset_tolerance_s: Maximum allowed difference in note start time (s)
            for two notes to be considered a match.
        midi_tolerance: Maximum allowed MIDI pitch difference (semitones).

    Returns:
        :class:`RhythmComparisonResult` with per-matched-note and aggregate
        metrics.
    """
    reference_note_count = len(reference_note_events)

    if reference_note_count == 0 or not user_note_events:
        logger.debug(
            "rhythm_comparison.empty ref_notes=%d user_notes=%d",
            reference_note_count,
            len(user_note_events),
        )
        return RhythmComparisonResult(
            onset_deviations_ms=[],
            duration_ratios=[],
            mean_onset_error_ms=0.0,
            rhythmic_consistency_ms=0.0,
            note_hit_rate=0.0,
            matched_note_count=0,
            reference_note_count=reference_note_count,
        )

    # Pre-sort user notes by start time for efficient search.
    sorted_user = sorted(
        user_note_events,
        key=lambda e: float(e.get("start_s") or e.get("start") or 0.0),
    )
    user_starts = [float(e.get("start_s") or e.get("start") or 0.0) for e in sorted_user]

    onset_deviations_ms: List[float] = []
    duration_ratios: List[float] = []
    matched = 0
    matched_user_indices: set = set()

    for ref_event in reference_note_events:
        ref_start = float(ref_event.get("start_s") or ref_event.get("start") or 0.0)
        ref_midi = float(ref_event.get("midi") or ref_event.get("pitch") or 0.0)
        ref_dur = float(
            ref_event.get("duration_s")
            or ref_event.get("duration")
            or max(
                (float(ref_event.get("end_s") or ref_event.get("end") or ref_start) - ref_start),
                0.0,
            )
        )

        # Binary-search for the user note closest in start time.
        candidate_idx = _find_nearest_onset_idx(user_starts, ref_start)
        if candidate_idx is None:
            continue

        # Expand search around candidate to find the best match within tolerances.
        best_user: Optional[Dict] = None
        best_delta_s: float = float("inf")
        best_user_idx: Optional[int] = None

        for idx in _search_range(candidate_idx, len(sorted_user)):
            if idx in matched_user_indices:
                continue
            u_start = user_starts[idx]
            if abs(u_start - ref_start) > onset_tolerance_s:
                # Since user_starts is sorted, stop if we're too far in one direction.
                if u_start - ref_start > onset_tolerance_s:
                    break
                continue

            u_event = sorted_user[idx]
            u_midi = float(u_event.get("midi") or u_event.get("pitch") or 0.0)

            if abs(u_midi - ref_midi) > midi_tolerance:
                continue

            delta_s = abs(u_start - ref_start)
            if delta_s < best_delta_s:
                best_delta_s = delta_s
                best_user = u_event
                best_user_idx = idx

        if best_user is None:
            continue

        if best_user_idx is not None:
            matched_user_indices.add(best_user_idx)

        matched += 1
        u_start = float(best_user.get("start_s") or best_user.get("start") or 0.0)
        u_dur = float(
            best_user.get("duration_s")
            or best_user.get("duration")
            or max(
                (float(best_user.get("end_s") or best_user.get("end") or u_start) - u_start),
                0.0,
            )
        )

        onset_deviations_ms.append((u_start - ref_start) * 1000.0)
        duration_ratios.append(u_dur / ref_dur if ref_dur > 0.0 else 1.0)

    note_hit_rate = float(matched) / float(reference_note_count) if reference_note_count > 0 else 0.0
    dev_arr = np.asarray(onset_deviations_ms, dtype=float) if onset_deviations_ms else np.array([], dtype=float)

    mean_onset_error_ms = float(np.mean(np.abs(dev_arr))) if dev_arr.size else 0.0
    rhythmic_consistency_ms = float(np.std(dev_arr)) if dev_arr.size else 0.0

    logger.debug(
        "rhythm_comparison.result ref_notes=%d matched=%d hit_rate=%.3f moe_ms=%.2f consistency_ms=%.2f",
        reference_note_count,
        matched,
        note_hit_rate,
        mean_onset_error_ms,
        rhythmic_consistency_ms,
    )

    return RhythmComparisonResult(
        onset_deviations_ms=onset_deviations_ms,
        duration_ratios=duration_ratios,
        mean_onset_error_ms=mean_onset_error_ms,
        rhythmic_consistency_ms=rhythmic_consistency_ms,
        note_hit_rate=note_hit_rate,
        matched_note_count=matched,
        reference_note_count=reference_note_count,
    )


def _find_nearest_onset_idx(sorted_starts: List[float], target: float) -> Optional[int]:
    """Binary-search *sorted_starts* and return the index nearest to *target*."""
    if not sorted_starts:
        return None
    lo, hi = 0, len(sorted_starts) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_starts[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    best = lo
    if lo > 0 and abs(sorted_starts[lo - 1] - target) <= abs(sorted_starts[lo] - target):
        best = lo - 1
    return best


def _search_range(center: int, length: int):
    """Yield indices radiating outward from *center* within [0, length)."""
    yield center
    for offset in range(1, length):
        left = center - offset
        right = center + offset
        if left < 0 and right >= length:
            break
        if left >= 0:
            yield left
        if right < length:
            yield right
