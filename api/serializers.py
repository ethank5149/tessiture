"""
Result serialization and formatting functions for the Tessiture API.

This module contains functions for formatting, serialization, and summary building
of analysis results. These functions transform raw analysis data structures into
client-friendly payload formats with proper note annotations and metadata.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from api.config import NOTE_NAMES
from api.pitch_utils import (_hz_to_note_name, _midi_to_note_name,
                             _midi_values_to_note_names)
from api.utils import _is_voiced_frame, _safe_float

logger = logging.getLogger(__name__)


def _format_timestamp_label(seconds: Any) -> str:
    """Format seconds as MM:SS timestamp label."""
    timestamp = _safe_float(seconds)
    if timestamp is None or timestamp < 0.0:
        return "00:00"
    rounded_seconds = int(float(np.floor(float(timestamp))))
    minutes = rounded_seconds // 60
    remainder = rounded_seconds % 60
    return f"{minutes:02d}:{remainder:02d}"


def _serialize_tessitura_payload(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    metrics = getattr(payload, "metrics", None)
    pdf = getattr(payload, "pdf", None)
    if metrics is None:
        return {}

    strain_zones = []
    for zone in getattr(metrics, "strain_zones", ()):
        strain_zones.append(
            {
                "label": getattr(zone, "label", None),
                "low": _safe_float(getattr(zone, "low", None)),
                "high": _safe_float(getattr(zone, "high", None)),
                "reason": getattr(zone, "reason", None),
            }
        )

    range_min = _safe_float(getattr(metrics, "range_min", None))
    range_max = _safe_float(getattr(metrics, "range_max", None))
    tessitura_band = list(getattr(metrics, "tessitura_band", ()))
    comfort_band = list(getattr(metrics, "comfort_band", ()))
    comfort_center = _safe_float(getattr(metrics, "comfort_center", None))

    serialized: Dict[str, Any] = {
        "metrics": {
            "count": int(getattr(metrics, "count", 0)),
            "weight_sum": _safe_float(getattr(metrics, "weight_sum", None)),
            "range_min": range_min,
            "range_max": range_max,
            "range_min_note": _midi_to_note_name(range_min) if range_min is not None else None,
            "range_max_note": _midi_to_note_name(range_max) if range_max is not None else None,
            "tessitura_band": tessitura_band,
            "tessitura_band_notes": _midi_values_to_note_names(tessitura_band),
            "comfort_band": comfort_band,
            "comfort_band_notes": _midi_values_to_note_names(comfort_band),
            "comfort_center": comfort_center,
            "comfort_center_note": _midi_to_note_name(comfort_center) if comfort_center is not None else None,
            "variance": _safe_float(getattr(metrics, "variance", None)),
            "std_dev": _safe_float(getattr(metrics, "std_dev", None)),
            "mean_variance": _safe_float(getattr(metrics, "mean_variance", None)),
            "strain_zones": strain_zones,
        }
    }

    if pdf is not None:
        density = np.asarray(getattr(pdf, "density", []), dtype=float).tolist()
        serialized["pdf"] = {
            "bin_edges": np.asarray(getattr(pdf, "bin_edges", []), dtype=float).tolist(),
            "density": density,
            "bin_centers": np.asarray(getattr(pdf, "bin_centers", []), dtype=float).tolist(),
            "bin_size": _safe_float(getattr(pdf, "bin_size", None)),
            "total_weight": _safe_float(getattr(pdf, "total_weight", None)),
        }
        # Backward-compatible aliases expected by some clients.
        serialized["histogram"] = density
        serialized["heatmap"] = density
    return serialized


def _summarize_formants(track: Any) -> Dict[str, Any]:
    if track is None:
        return {}
    f1 = np.asarray(getattr(track, "f1_hz", []), dtype=float)
    f2 = np.asarray(getattr(track, "f2_hz", []), dtype=float)
    f3 = np.asarray(getattr(track, "f3_hz", []), dtype=float)
    return {
        "n_frames": int(f1.size),
        "f1_hz_mean": _safe_float(np.mean(f1) if f1.size else None),
        "f2_hz_mean": _safe_float(np.mean(f2) if f2.size else None),
        "f3_hz_mean": _safe_float(np.mean(f3) if f3.size else None),
    }


def _summarize_phrases(phrase_result: Any) -> Dict[str, Any]:
    boundaries = []
    for boundary in getattr(phrase_result, "boundaries", []):
        boundaries.append(
            {
                "time_s": _safe_float(getattr(boundary, "time_s", None)),
                "confidence": _safe_float(getattr(boundary, "confidence", None)),
                "index": int(getattr(boundary, "index", 0)),
                "kind": getattr(boundary, "kind", None),
            }
        )
    return {
        "threshold_db": _safe_float(getattr(phrase_result, "threshold_db", None)),
        "boundary_count": len(boundaries),
        "boundaries": boundaries,
    }


def _build_summary(result: Mapping[str, Any], duration_seconds: float) -> Dict[str, Any]:
    pitch_frames = result.get("pitch", {}).get("frames", []) if isinstance(result, Mapping) else []
    voiced_frames = [item for item in pitch_frames if _is_voiced_frame(item)]
    voiced_f0 = [float(item["f0_hz"]) for item in voiced_frames]
    confidences = [
        float(item["confidence"])
        for item in voiced_frames
        if _safe_float(item.get("confidence")) is not None
    ]
    mean_confidence = float(np.mean(confidences)) if confidences else 0.0

    tessitura_metrics = result.get("tessitura", {}).get("metrics", {}) if isinstance(result, Mapping) else {}
    tessitura_band = tessitura_metrics.get("tessitura_band") if isinstance(tessitura_metrics, Mapping) else []
    tessitura_range_notes: Optional[List[str]] = None
    if isinstance(tessitura_band, Sequence) and not isinstance(tessitura_band, (str, bytes)):
        candidate_notes = [note for note in _midi_values_to_note_names(list(tessitura_band)[:2]) if note is not None]
        if len(candidate_notes) == 2:
            tessitura_range_notes = candidate_notes
    key_trajectory = result.get("keys", {}).get("trajectory", []) if isinstance(result, Mapping) else []
    key_confidence = 0.0
    if isinstance(key_trajectory, Sequence) and key_trajectory:
        key_confidence = _safe_float(key_trajectory[0].get("confidence")) or 0.0

    logger.info(
        "analysis_confidence_summary duration=%.3fs total_frames=%d voiced_frames=%d confidence_min=%.4f confidence_max=%.4f confidence_mean=%.4f key_confidence=%.4f",
        float(duration_seconds),
        len(pitch_frames),
        len(voiced_f0),
        float(np.min(confidences)) if confidences else 0.0,
        float(np.max(confidences)) if confidences else 0.0,
        mean_confidence,
        key_confidence,
    )

    return {
        "duration_seconds": float(duration_seconds),
        "f0_min": float(np.min(voiced_f0)) if voiced_f0 else None,
        "f0_max": float(np.max(voiced_f0)) if voiced_f0 else None,
        "f0_min_note": _hz_to_note_name(np.min(voiced_f0)) if voiced_f0 else None,
        "f0_max_note": _hz_to_note_name(np.max(voiced_f0)) if voiced_f0 else None,
        "tessitura_range": tessitura_band,
        "tessitura_range_notes": tessitura_range_notes,
        "confidence": mean_confidence,
        "pitch_confidence": mean_confidence,
        "key_confidence": key_confidence,
    }
