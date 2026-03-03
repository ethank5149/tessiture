"""Time alignment helpers for vocalist vs. reference pitch tracks."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum time gap (seconds) between a user frame and a reference frame for
# them to be considered "aligned" rather than unmatched.
ALIGNMENT_TOLERANCE_S: float = 0.05


def align_to_reference(
    user_pitch_track: List[Dict],
    reference_pitch_track: List[Dict],
    playback_offset_s: float = 0.0,
) -> List[Dict]:
    """Align user pitch frames to reference frames using fixed-time alignment.

    For each user frame at ``time_s``, the function searches the reference
    track for the frame whose ``time_s`` is closest to
    ``(user_time_s + playback_offset_s)``.  Frames with no reference match
    within :data:`ALIGNMENT_TOLERANCE_S` (0.05 s) are still included with
    ``reference=None``.

    Args:
        user_pitch_track: List of dicts with keys ``time_s``, ``f0_hz``,
            ``midi``, ``confidence`` (as produced by the pitch pipeline).
        reference_pitch_track: Same schema as *user_pitch_track*.
        playback_offset_s: Seconds to shift user time into reference time.
            Positive values mean the user started singing *after* the
            reference track began.

    Returns:
        List of aligned pair dicts::

            [
                {
                    "user": {...frame},       # original user frame
                    "reference": {...frame},  # nearest reference frame, or None
                    "time_s": float,         # user frame time_s
                }
            ]
    """
    if not reference_pitch_track:
        return [
            {"user": frame, "reference": None, "time_s": float(frame.get("time_s", 0.0))}
            for frame in user_pitch_track
        ]

    # Build a sorted list of reference times for O(n log n) lookup.
    ref_times = [float(f.get("time_s", 0.0)) for f in reference_pitch_track]

    aligned: List[Dict] = []
    for user_frame in user_pitch_track:
        user_time = float(user_frame.get("time_s", 0.0))
        target_ref_time = user_time + playback_offset_s

        # Binary-search for the closest reference frame.
        ref_frame = _find_nearest_frame(reference_pitch_track, ref_times, target_ref_time)

        if ref_frame is not None:
            delta = abs(float(ref_frame.get("time_s", 0.0)) - target_ref_time)
            if delta > ALIGNMENT_TOLERANCE_S:
                ref_frame = None

        aligned.append(
            {
                "user": user_frame,
                "reference": ref_frame,
                "time_s": user_time,
            }
        )

    logger.debug(
        "alignment.complete user_frames=%d aligned_with_ref=%d",
        len(user_pitch_track),
        sum(1 for p in aligned if p["reference"] is not None),
    )
    return aligned


def _find_nearest_frame(
    frames: List[Dict],
    times: List[float],
    query_time: float,
) -> Optional[Dict]:
    """Return the frame in *frames* whose time is closest to *query_time*.

    Uses binary search on *times* (pre-sorted, parallel to *frames*).
    """
    if not frames:
        return None

    lo, hi = 0, len(times) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if times[mid] < query_time:
            lo = mid + 1
        else:
            hi = mid

    # *lo* is now the insertion point.  Check lo and lo-1 for nearest.
    best_idx = lo
    if lo > 0 and abs(times[lo - 1] - query_time) <= abs(times[lo] - query_time):
        best_idx = lo - 1

    return frames[best_idx]


def interpolate_reference_at_time(
    reference_pitch_track: List[Dict],
    query_time_s: float,
) -> Optional[Dict]:
    """Return the reference frame at or nearest to *query_time_s*.

    If the query time falls between two reference frames, ``f0_hz`` is
    linearly interpolated; all other fields are copied from the nearest
    frame.  Returns ``None`` if *reference_pitch_track* is empty.

    Args:
        reference_pitch_track: List of dicts with ``time_s`` and ``f0_hz``.
        query_time_s: The time to query.

    Returns:
        A new dict combining nearest-frame metadata with interpolated
        ``f0_hz``, or ``None`` if the track is empty.
    """
    if not reference_pitch_track:
        return None

    ref_times = [float(f.get("time_s", 0.0)) for f in reference_pitch_track]

    # Find bracketing frames.
    lo, hi = 0, len(ref_times) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if ref_times[mid] < query_time_s:
            lo = mid + 1
        else:
            hi = mid

    # lo is the first index ≥ query_time_s.
    if lo == 0:
        return dict(reference_pitch_track[0])
    if lo >= len(ref_times):
        return dict(reference_pitch_track[-1])

    left_frame = reference_pitch_track[lo - 1]
    right_frame = reference_pitch_track[lo]
    t_lo = ref_times[lo - 1]
    t_hi = ref_times[lo]

    if t_hi <= t_lo:
        return dict(left_frame)

    # Linear interpolation of f0_hz.
    alpha = (query_time_s - t_lo) / (t_hi - t_lo)
    f0_left = float(left_frame.get("f0_hz") or 0.0)
    f0_right = float(right_frame.get("f0_hz") or 0.0)
    f0_interp = f0_left + alpha * (f0_right - f0_left)

    # Use nearest frame for non-numeric fields.
    nearest = left_frame if alpha <= 0.5 else right_frame
    result = dict(nearest)
    result["f0_hz"] = f0_interp
    result["time_s"] = query_time_s
    return result
