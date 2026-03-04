"""Time alignment helpers for vocalist vs. reference pitch tracks."""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

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

    # Geometric (log-linear) interpolation of f0_hz: perceptually linear in pitch space
    alpha = (query_time_s - t_lo) / (t_hi - t_lo)
    f0_left = float(left_frame.get("f0_hz") or 0.0)
    f0_right = float(right_frame.get("f0_hz") or 0.0)
    if f0_left > 0.0 and f0_right > 0.0:
        # Geometric interpolation: f0_left * (f0_right/f0_left)^alpha
        f0_interp = f0_left * ((f0_right / f0_left) ** alpha)
    elif f0_left > 0.0:
        f0_interp = f0_left
    elif f0_right > 0.0:
        f0_interp = f0_right
    else:
        f0_interp = 0.0

    # Use nearest frame for non-numeric fields.
    nearest = left_frame if alpha <= 0.5 else right_frame
    result = dict(nearest)
    result["f0_hz"] = f0_interp
    result["time_s"] = query_time_s
    return result

def _dtw_frame_distance(user_frame: Dict, ref_frame: Dict) -> float:
    """Compute distance between a user pitch frame and reference pitch frame.

    Distance metric:
    - If both unvoiced: 0.0 (no cost to be unvoiced together)
    - If one voiced, one unvoiced: 1.0 (voicing mismatch penalty)
    - If both voiced: |semitone distance| / 12.0 (normalized to 0-1 for 1 octave = 1)

    Args:
        user_frame: User pitch frame dict with 'f0_hz' key.
        ref_frame: Reference pitch frame dict with 'f0_hz' key.

    Returns:
        Distance in [0, 2] range.
    """
    u_f0 = float(user_frame.get("f0_hz") or 0.0)
    r_f0 = float(ref_frame.get("f0_hz") or 0.0)
    u_voiced = u_f0 > 0.0
    r_voiced = r_f0 > 0.0

    if not u_voiced and not r_voiced:
        return 0.0
    if u_voiced != r_voiced:
        return 1.0  # voicing mismatch

    # Both voiced — pitch distance in semitones, normalized
    try:
        semitones = abs(12.0 * math.log2(u_f0 / r_f0))
    except (ValueError, ZeroDivisionError):
        return 1.0
    return semitones / 12.0  # normalize: 1 octave = 1.0


def _dtw_compute_path(
    user_frames: List[Dict],
    reference_frames: List[Dict],
    bandwidth: Optional[int] = None,
) -> List[Tuple[int, int]]:
    """Compute DTW warping path between user and reference pitch frame sequences.

    Implements standard DTW with optional Sakoe-Chiba bandwidth constraint to
    prevent extreme warping.

    Args:
        user_frames: User pitch frames (dicts with 'f0_hz').
        reference_frames: Reference pitch frames (dicts with 'f0_hz').
        bandwidth: Sakoe-Chiba band width in frames. None = unconstrained.

    Returns:
        List of (user_idx, ref_idx) tuples representing the warping path.
    """
    n = len(user_frames)
    m = len(reference_frames)

    if n == 0 or m == 0:
        return []

    INF = float("inf")

    # Cumulative cost matrix
    C = np.full((n, m), INF, dtype=np.float32)

    # Pre-compute distance matrix (or compute on the fly with bandwidth)
    for i in range(n):
        j_min = 0 if bandwidth is None else max(0, i - bandwidth)
        j_max = m if bandwidth is None else min(m, i + bandwidth + 1)
        for j in range(j_min, j_max):
            d = _dtw_frame_distance(user_frames[i], reference_frames[j])
            if i == 0 and j == 0:
                C[i, j] = d
            elif i == 0:
                if j_min == 0:  # j=0 is in range for i=0
                    prev = C[0, j - 1] if j > 0 else INF
                    C[i, j] = d + prev
            elif j == 0:
                C[i, j] = d + C[i - 1, 0] if i > 0 else d
            else:
                candidates = []
                if C[i - 1, j - 1] < INF:
                    candidates.append(C[i - 1, j - 1])
                if C[i - 1, j] < INF:
                    candidates.append(C[i - 1, j])
                if C[i, j - 1] < INF:
                    candidates.append(C[i, j - 1])
                C[i, j] = d + (min(candidates) if candidates else INF)

    # Backtrace from (n-1, m-1)
    path = []
    i, j = n - 1, m - 1

    if C[i, j] == INF:
        # No valid path — fall back to linear path
        for k in range(max(n, m)):
            path.append((min(k, n - 1), min(k, m - 1)))
        return path

    path.append((i, j))
    while i > 0 or j > 0:
        if i == 0:
            j -= 1
        elif j == 0:
            i -= 1
        else:
            best = np.argmin([C[i - 1, j - 1], C[i - 1, j], C[i, j - 1]])
            if best == 0:
                i -= 1; j -= 1
            elif best == 1:
                i -= 1
            else:
                j -= 1
        path.append((i, j))

    path.reverse()
    return path


def align_to_reference_dtw(
    user_pitch_track: List[Dict],
    reference_pitch_track: List[Dict],
    bandwidth_s: Optional[float] = 2.0,
    hop_s: float = 512.0 / 44100.0,
) -> List[Dict]:
    """Align user pitch frames to reference frames using Dynamic Time Warping.

    Unlike the fixed-time `align_to_reference()`, DTW finds the globally optimal
    non-linear warping between the two sequences, handling tempo variations,
    rubato, and phrase-level timing differences.

    Algorithm: Standard DTW with optional Sakoe-Chiba band constraint
    (Müller, M., "Information Retrieval for Music and Motion", Springer, 2007).

    Args:
        user_pitch_track: List of dicts with keys 'time_s', 'f0_hz', etc.
        reference_pitch_track: List of dicts with keys 'time_s', 'f0_hz', etc.
        bandwidth_s: Maximum allowed time deviation (seconds) for Sakoe-Chiba
            bandwidth constraint. None = unconstrained DTW. Default 2.0s.
        hop_s: Frame hop duration in seconds (for bandwidth conversion to frames).

    Returns:
        List of aligned pair dicts, same schema as `align_to_reference()`:
        [{"user": frame, "reference": frame_or_None, "time_s": float}]

    Notes:
        - Every user frame gets a reference match (no None references) unless
          the sequences are empty.
        - The warping path ensures monotonicity: time always moves forward in
          both sequences.
    """
    if not reference_pitch_track:
        return [
            {"user": frame, "reference": None, "time_s": float(frame.get("time_s", 0.0))}
            for frame in user_pitch_track
        ]

    if not user_pitch_track:
        return []

    # Convert bandwidth from seconds to frames
    bandwidth_frames = None
    if bandwidth_s is not None and hop_s > 0.0:
        bandwidth_frames = max(1, int(round(float(bandwidth_s) / float(hop_s))))

    path = _dtw_compute_path(user_pitch_track, reference_pitch_track, bandwidth=bandwidth_frames)

    # Map warping path to aligned pair format
    # path is a list of (user_idx, ref_idx)
    # Multiple user frames may map to the same ref frame (compression)
    # Multiple ref frames may map to the same user frame (expansion)

    # Build a user_idx → ref_idx mapping from the path
    user_to_ref: Dict[int, int] = {}
    for u_idx, r_idx in path:
        user_to_ref[u_idx] = r_idx  # last occurrence wins (fine for warping)

    aligned: List[Dict] = []
    for user_idx, user_frame in enumerate(user_pitch_track):
        ref_idx = user_to_ref.get(user_idx)
        ref_frame = reference_pitch_track[ref_idx] if ref_idx is not None else None
        aligned.append({
            "user": user_frame,
            "reference": ref_frame,
            "time_s": float(user_frame.get("time_s", 0.0)),
        })

    logger.debug(
        "alignment.dtw.complete user_frames=%d ref_frames=%d path_length=%d",
        len(user_pitch_track),
        len(reference_pitch_track),
        len(path),
    )

    return aligned
