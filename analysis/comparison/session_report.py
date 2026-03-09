"""Session report aggregation for post-session comparison analysis."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from analysis.comparison.pitch_comparison import compare_pitch_tracks, PitchComparisonResult
from analysis.comparison.rhythm_comparison import compare_note_timing, RhythmComparisonResult
from analysis.comparison.range_comparison import compare_vocal_ranges, RangeComparisonResult
from analysis.comparison.formant_comparison import compare_formants, FormantComparisonResult

logger = logging.getLogger(__name__)

# Semitone tolerance for grouping consecutive voiced frames into note events.
_NOTE_GROUPING_SEMITONE_TOLERANCE: float = 2.0
# Minimum duration (seconds) for a run to be considered a note event.
_MIN_NOTE_DURATION_S: float = 0.05
_VOICED_MIN_HZ: float = float(os.getenv("TESSITURE_VOICED_MIN_HZ", "80.0"))
_VOICED_MAX_HZ: float = float(os.getenv("TESSITURE_VOICED_MAX_HZ", "1200.0"))


@dataclass(frozen=True)
class SessionReport:
    """Complete post-session comparison report."""

    session_id: str
    reference_id: str
    reference_source: str           # "upload" or "example"
    reference_source_id: str        # filename or example_id
    reference_key: Optional[str]    # musical key of reference
    session_started_at: str         # ISO 8601 datetime
    session_duration_s: float
    total_chunks_processed: int
    voiced_chunks: int
    # All comparison results serialized as dicts
    pitch_comparison: Dict[str, Any]
    rhythm_comparison: Dict[str, Any]
    range_comparison: Dict[str, Any]
    formant_comparison: Dict[str, Any]


def _reconstruct_user_note_events(voiced_frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group contiguous voiced frames into note events.

    Args:
        voiced_frames: List of dicts with ``time_s``, ``f0_hz``, ``midi``,
            ``note_name``, ``confidence`` keys (all voiced).

    Returns:
        List of note event dicts with ``start_s``, ``end_s``, ``midi``,
        ``note_name``, ``duration_s``.
    """
    if not voiced_frames:
        return []

    note_events: List[Dict[str, Any]] = []
    # Sort by time to be safe.
    frames = sorted(voiced_frames, key=lambda f: float(f.get("time_s", 0.0)))

    # Estimate frame hop from adjacent frames (default 0.032 s ≈ 32 ms chunks).
    if len(frames) >= 2:
        hop_s = float(frames[1].get("time_s", 0.0)) - float(frames[0].get("time_s", 0.0))
        if hop_s <= 0.0:
            hop_s = 0.032
    else:
        hop_s = 0.032

    group_start_s: float = float(frames[0].get("time_s", 0.0))
    group_midi: float = float(frames[0].get("midi") or 0.0)
    group_note_name: str = str(frames[0].get("note_name") or "")
    group_end_s: float = group_start_s + hop_s

    for frame in frames[1:]:
        t = float(frame.get("time_s", 0.0))
        midi = float(frame.get("midi") or 0.0)
        note_name = str(frame.get("note_name") or "")

        if abs(midi - group_midi) <= _NOTE_GROUPING_SEMITONE_TOLERANCE:
            # Extend the current group.
            group_end_s = t + hop_s
        else:
            # Flush current group if long enough.
            dur = group_end_s - group_start_s
            if dur >= _MIN_NOTE_DURATION_S:
                note_events.append(
                    {
                        "start_s": group_start_s,
                        "end_s": group_end_s,
                        "midi": group_midi,
                        "note_name": group_note_name,
                        "duration_s": dur,
                    }
                )
            group_start_s = t
            group_midi = midi
            group_note_name = note_name
            group_end_s = t + hop_s

    # Flush final group.
    dur = group_end_s - group_start_s
    if dur >= _MIN_NOTE_DURATION_S:
        note_events.append(
            {
                "start_s": group_start_s,
                "end_s": group_end_s,
                "midi": group_midi,
                "note_name": group_note_name,
                "duration_s": dur,
            }
        )

    return note_events


def _build_aligned_pairs_from_chunks(chunk_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert chunk_results into aligned_pairs format expected by compare_pitch_tracks.

    Each chunk already carries ``pitch_deviation_cents`` and both f0 values,
    so we reconstruct aligned pairs directly.

    Args:
        chunk_results: List of chunk_feedback dicts from the streaming session.

    Returns:
        List of aligned pair dicts with ``time_s``, ``user`` and ``reference`` sub-dicts.
    """
    pairs: List[Dict[str, Any]] = []
    for chunk in chunk_results:
        user_f0 = chunk.get("user_f0_hz")
        ref_f0 = chunk.get("reference_f0_hz")
        t = chunk.get("timestamp_s", 0.0)

        if user_f0 is None or ref_f0 is None:
            continue
        try:
            user_f0_f = float(user_f0)
            ref_f0_f = float(ref_f0)
        except (TypeError, ValueError):
            continue
        if not _is_voiced_f0(user_f0_f) or not _is_voiced_f0(ref_f0_f):
            continue

        pairs.append(
            {
                "time_s": float(t),
                "user": {"f0_hz": user_f0_f},
                "reference": {"f0_hz": ref_f0_f},
            }
        )
    return pairs


def build_session_report(
    session_id: str,
    reference_id: str,
    reference_source: str,
    reference_source_id: str,
    reference_key: Optional[str],
    session_started_at: str,
    session_duration_s: float,
    chunk_results: List[Dict[str, Any]],
    reference_note_events: List[Dict[str, Any]],
    reference_formant_summary: Optional[Dict[str, Any]],
    reference_tessitura_center_midi: Optional[float],
) -> SessionReport:
    """Aggregate chunk-level session data into a complete comparison report.

    Args:
        session_id: Unique identifier for the comparison session.
        reference_id: Cache key / identifier for the reference track.
        reference_source: ``"upload"`` or ``"example"``.
        reference_source_id: Filename (upload) or example_id (example).
        reference_key: Musical key string from the reference analysis, or ``None``.
        session_started_at: ISO 8601 datetime string marking session start.
        session_duration_s: Total session duration in seconds.
        chunk_results: List of chunk_feedback dicts from the streaming session.
            Each dict has: ``timestamp_s``, ``user_f0_hz``, ``user_midi``,
            ``user_note_name``, ``user_confidence``, ``reference_f0_hz``,
            ``reference_midi``, ``reference_note_name``, ``pitch_deviation_cents``,
            ``in_tune``.
        reference_note_events: From ``ReferenceAnalysis.note_events``.
        reference_formant_summary: From ``ReferenceAnalysis.formant_summary``, or ``None``.
        reference_tessitura_center_midi: From ``ReferenceAnalysis.tessitura_center_midi``,
            or ``None``.

    Returns:
        :class:`SessionReport` with all comparison results populated.
    """
    total_chunks = len(chunk_results)

    # --- voiced chunks ---
    voiced_chunks = sum(
        1
        for c in chunk_results
        if c.get("user_f0_hz") is not None
        and _is_voiced_f0(c.get("user_f0_hz"))
    )

    # --- reconstruct voiced pitch track ---
    voiced_frames: List[Dict[str, Any]] = []
    for chunk in chunk_results:
        user_f0 = chunk.get("user_f0_hz")
        if user_f0 is None or not _is_voiced_f0(user_f0):
            continue
        voiced_frames.append(
            {
                "time_s": float(chunk.get("timestamp_s", 0.0)),
                "f0_hz": float(user_f0),
                "midi": chunk.get("user_midi"),
                "note_name": chunk.get("user_note_name"),
                "confidence": chunk.get("user_confidence"),
            }
        )

    # --- build comparison inputs ---
    user_voiced_midi: List[float] = [
        float(f["midi"])
        for f in voiced_frames
        if f.get("midi") is not None and math.isfinite(float(f["midi"]))
    ]

    user_note_events = _reconstruct_user_note_events(voiced_frames)
    aligned_pairs = _build_aligned_pairs_from_chunks(chunk_results)

    # --- pitch comparison ---
    pitch_result: PitchComparisonResult = compare_pitch_tracks(aligned_pairs)

    # --- rhythm comparison ---
    rhythm_result: RhythmComparisonResult = compare_note_timing(
        user_note_events, reference_note_events
    )

    # --- range comparison ---
    # Build a minimal tessitura_metrics dict if we have a reference center.
    user_tessitura_metrics: Optional[Dict[str, Any]] = None
    if reference_tessitura_center_midi is not None and user_voiced_midi:
        # Use the midpoint of the user's voiced range as a comfort center proxy.
        user_center = (min(user_voiced_midi) + max(user_voiced_midi)) / 2.0
        user_tessitura_metrics = {"comfort_center": user_center}

    range_result: RangeComparisonResult = compare_vocal_ranges(
        user_voiced_midi, reference_note_events, user_tessitura_metrics
    )

    # --- formant comparison ---
    # Formant data is unavailable in streaming mode — user_formant_summary is always None.
    formant_result: FormantComparisonResult = compare_formants(None, reference_formant_summary)

    logger.debug(
        "session_report.built session_id=%s total_chunks=%d voiced_chunks=%d",
        session_id,
        total_chunks,
        voiced_chunks,
    )

    return SessionReport(
        session_id=session_id,
        reference_id=reference_id,
        reference_source=reference_source,
        reference_source_id=reference_source_id,
        reference_key=reference_key,
        session_started_at=session_started_at,
        session_duration_s=session_duration_s,
        total_chunks_processed=total_chunks,
        voiced_chunks=voiced_chunks,
        pitch_comparison=asdict(pitch_result),
        rhythm_comparison=asdict(rhythm_result),
        range_comparison=asdict(range_result),
        formant_comparison=asdict(formant_result),
    )


def session_report_to_dict(report: SessionReport) -> Dict[str, Any]:
    """Convert :class:`SessionReport` to a JSON-serializable dict."""
    return asdict(report)


def _is_voiced_f0(f0: Any) -> bool:
    """Return True if *f0* is finite and inside the configured voiced-frequency band."""
    try:
        f0_f = float(f0)
        return math.isfinite(f0_f) and _VOICED_MIN_HZ <= f0_f <= _VOICED_MAX_HZ
    except (TypeError, ValueError):
        return False


__all__ = [
    "SessionReport",
    "build_session_report",
    "session_report_to_dict",
]
