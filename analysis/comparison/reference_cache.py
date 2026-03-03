"""In-memory cache for pre-analyzed reference tracks."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class ReferenceSource(str, Enum):
    """Source type for a reference track."""

    upload = "upload"
    example = "example"


@dataclass
class ReferenceAnalysis:
    """Full pipeline output for a cached reference track plus derived ground-truth summary."""

    reference_id: str
    """Unique identifier (uuid4 hex) assigned at cache-store time."""

    source: str
    """Source kind: 'upload' or 'example'."""

    source_id: str
    """Filename (for uploads) or example_id (for gallery examples)."""

    analysis: Dict[str, Any]
    """Raw dict returned by _run_analysis_pipeline() → result['analysis']."""

    pitch_track: List[Dict[str, Any]]
    """Voiced pitch frames: [{ time_s, f0_hz, midi, note_name, confidence }]."""

    note_events: List[Dict[str, Any]]
    """Note events: [{ start_s, end_s, midi, note_name, duration_s }]."""

    duration_s: float
    """Audio duration in seconds."""

    key: Optional[str]
    """Best-detected key string (e.g. 'C major'), or None."""

    tessitura_center_midi: Optional[float]
    """Comfort-center MIDI value from tessitura analysis, or None."""

    formant_summary: Optional[Dict[str, Any]]
    """Dict with mean_f1_hz / mean_f2_hz, or None if unavailable."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Module-level singleton — intentionally simple dict, no TTL.
# ---------------------------------------------------------------------------
_CACHE: Dict[str, ReferenceAnalysis] = {}


def store(analysis: ReferenceAnalysis) -> str:
    """Store a ReferenceAnalysis in the cache.  Returns the reference_id."""
    _CACHE[analysis.reference_id] = analysis
    logger.info(
        "reference_cache.stored reference_id=%s source=%s source_id=%s duration_s=%.2f",
        analysis.reference_id,
        analysis.source,
        analysis.source_id,
        analysis.duration_s,
    )
    return analysis.reference_id


def get(reference_id: str) -> Optional[ReferenceAnalysis]:
    """Return the cached ReferenceAnalysis, or None if not found."""
    return _CACHE.get(reference_id)


def exists(reference_id: str) -> bool:
    """Return True if *reference_id* is present in the cache."""
    return reference_id in _CACHE


def list_all() -> List[ReferenceAnalysis]:
    """Return all cached ReferenceAnalysis objects (insertion order preserved on Python 3.7+)."""
    return list(_CACHE.values())


def delete(reference_id: str) -> bool:
    """Remove *reference_id* from the cache.  Returns True if it was present, False otherwise."""
    if reference_id in _CACHE:
        del _CACHE[reference_id]
        logger.info("reference_cache.deleted reference_id=%s", reference_id)
        return True
    return False


# ---------------------------------------------------------------------------
# Factory helper used by the API layer to build a ReferenceAnalysis from the
# raw pipeline result dict (result["analysis"]).
# ---------------------------------------------------------------------------

def build_reference_analysis(
    *,
    source: str,
    source_id: str,
    pipeline_result: Dict[str, Any],
) -> ReferenceAnalysis:
    """Construct a :class:`ReferenceAnalysis` from a pipeline result dict.

    *pipeline_result* is expected to be ``result["analysis"]`` from
    ``_run_analysis_pipeline()``.
    """
    analysis = pipeline_result  # already the inner "analysis" dict

    # --- pitch track (voiced frames only) ---
    raw_frames: List[Dict[str, Any]] = analysis.get("pitch", {}).get("frames", []) or []
    pitch_track: List[Dict[str, Any]] = []
    for frame in raw_frames:
        midi = frame.get("midi")
        f0 = frame.get("f0_hz") or frame.get("f0")
        if midi is None or f0 is None or float(f0) <= 0.0:
            continue
        pitch_track.append(
            {
                "time_s": float(frame.get("time") or frame.get("time_s") or 0.0),
                "f0_hz": float(f0),
                "midi": float(midi),
                "note_name": frame.get("note_name") or frame.get("note"),
                "confidence": float(frame.get("confidence") or 0.0),
            }
        )

    # --- note events ---
    raw_events: List[Dict[str, Any]] = analysis.get("note_events", []) or []
    note_events: List[Dict[str, Any]] = []
    for ev in raw_events:
        start = float(ev.get("start_s") or ev.get("start") or 0.0)
        end = float(ev.get("end_s") or ev.get("end") or start)
        midi_val = ev.get("midi") or ev.get("pitch")
        if midi_val is None:
            continue
        duration = float(ev.get("duration_s") or ev.get("duration") or max(end - start, 0.0))
        note_events.append(
            {
                "start_s": start,
                "end_s": end,
                "midi": float(midi_val),
                "note_name": ev.get("note_name") or ev.get("note"),
                "duration_s": duration,
            }
        )

    # --- duration ---
    duration_s = float(
        analysis.get("metadata", {}).get("duration_seconds")
        or analysis.get("summary", {}).get("duration_seconds")
        or 0.0
    )

    # --- key ---
    key: Optional[str] = analysis.get("keys", {}).get("best_key") or None
    if not key:
        trajectory = analysis.get("keys", {}).get("trajectory", [])
        if trajectory:
            key = trajectory[0].get("label") or None

    # --- tessitura center ---
    tessitura_center_midi: Optional[float] = None
    tess_metrics = analysis.get("tessitura", {}).get("metrics", {})
    if tess_metrics:
        comfort_center = tess_metrics.get("comfort_center")
        if comfort_center is not None:
            tessitura_center_midi = float(comfort_center)

    # --- formant summary ---
    formant_summary: Optional[Dict[str, Any]] = None
    formants_raw = analysis.get("advanced", {}).get("formants", {})
    if formants_raw:
        f1 = formants_raw.get("f1_hz_mean")
        f2 = formants_raw.get("f2_hz_mean")
        if f1 is not None and f2 is not None:
            formant_summary = {
                "mean_f1_hz": float(f1),
                "mean_f2_hz": float(f2),
            }

    reference_id = uuid4().hex
    return ReferenceAnalysis(
        reference_id=reference_id,
        source=source,
        source_id=source_id,
        analysis=analysis,
        pitch_track=pitch_track,
        note_events=note_events,
        duration_s=duration_s,
        key=key,
        tessitura_center_midi=tessitura_center_midi,
        formant_summary=formant_summary,
    )


# Expose a public class alias so that ``from analysis.comparison.reference_cache import ReferenceCache``
# works as documented in the __init__.py scaffold.
ReferenceCache = _CACHE  # type: ignore[assignment]
