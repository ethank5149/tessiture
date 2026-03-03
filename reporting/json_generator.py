"""JSON export generator for analysis reporting (Phase 6.2).

This module normalizes a flexible analysis result dictionary into a structured
JSON payload with frame-level pitch, note events, chord timeline, key trajectory,
tessitura metrics, uncertainty bounds, and metadata. Missing optional fields are
handled gracefully.
"""

from __future__ import annotations

import json
import math
from typing import Any, Mapping, MutableMapping, Optional, Sequence


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _coerce_sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _first_float(mapping: Mapping[str, Any], keys: Sequence[str]) -> Optional[float]:
    for key in keys:
        if key not in mapping:
            continue
        value = _safe_float(mapping.get(key))
        if value is not None:
            return value
    return None


def _ensure_mapping(value: Any) -> MutableMapping[str, Any]:
    if isinstance(value, MutableMapping):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _extract_frames(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for path in (
        ("frames",),
        ("pitch", "frames"),
        ("pitch_frames",),
        ("pitch", "pitch_frames"),
        ("analysis", "frames"),
    ):
        current: Any = result
        for key in path:
            if not isinstance(current, Mapping) or key not in current:
                current = None
                break
            current = current[key]
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            return [item for item in current if isinstance(item, Mapping)]
    return []


def _extract_events(result: Mapping[str, Any], *path: str) -> list[Mapping[str, Any]]:
    current: Any = result
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return []
        current = current[key]
    if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
        return []
    return [item for item in current if isinstance(item, Mapping)]


def _normalize_frame(frame: Mapping[str, Any], index: int, metadata: Mapping[str, Any]) -> dict[str, Any]:
    time_value = _first_float(frame, ("time", "timestamp", "t"))
    if time_value is None:
        frame_rate = _safe_float(metadata.get("frame_rate"))
        if frame_rate and frame_rate > 0:
            time_value = float(index / frame_rate)
        else:
            sample_rate = _safe_float(metadata.get("sample_rate"))
            hop_length = _first_float(metadata, ("hop_length", "frame_hop"))
            if sample_rate and hop_length:
                time_value = float(index * hop_length / sample_rate)
            else:
                time_value = float(index)
    return {
        "index": index,
        "time": time_value,
        "f0_hz": _first_float(frame, ("f0", "f0_hz", "frequency_hz")),
        "midi": _first_float(frame, ("midi", "midi_value")),
        "note": frame.get("note") or frame.get("note_name"),
        "cents": _first_float(frame, ("cents", "cents_deviation")),
        "confidence": _first_float(frame, ("confidence", "salience", "probability")),
        "uncertainty": _first_float(frame, ("uncertainty", "midi_uncertainty")),
    }


def _normalize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "start": _first_float(event, ("start", "time", "t")),
        "end": _safe_float(event.get("end")),
        "label": event.get("label") or event.get("chord") or event.get("key") or event.get("name"),
        "confidence": _first_float(event, ("confidence", "probability")),
    }


def _normalize_tessitura(metrics: Any) -> dict[str, Any]:
    if not isinstance(metrics, Mapping):
        return {}
    return {
        "count": metrics.get("count"),
        "weight_sum": _safe_float(metrics.get("weight_sum")),
        "range_min": _safe_float(metrics.get("range_min")),
        "range_max": _safe_float(metrics.get("range_max")),
        "tessitura_band": metrics.get("tessitura_band"),
        "comfort_band": metrics.get("comfort_band"),
        "comfort_center": _safe_float(metrics.get("comfort_center")),
        "variance": _safe_float(metrics.get("variance")),
        "std_dev": _safe_float(metrics.get("std_dev")),
        "mean_variance": _safe_float(metrics.get("mean_variance")),
        "strain_zones": _coerce_sequence(metrics.get("strain_zones")),
    }


def _normalize_uncertainty(result: Mapping[str, Any]) -> dict[str, Any]:
    bounds = result.get("uncertainty") or result.get("uncertainties") or {}
    if isinstance(bounds, Mapping):
        return {
            "pitch": bounds.get("pitch") or bounds.get("midi") or bounds.get("f0"),
            "confidence_intervals": bounds.get("confidence_intervals") or bounds.get("ci"),
        }
    return {}


def generate_json_report(result: Mapping[str, Any], output_path: Optional[str] = None, *, indent: int = 2) -> str:
    """Generate Phase 6.2 JSON export.

    Args:
        result: Analysis result dictionary (flexible schema).
        output_path: Optional path to write the JSON to disk.
        indent: JSON indentation level (default 2).

    Returns:
        JSON string containing structured reporting data.
    """
    metadata = _ensure_mapping(result.get("metadata") if isinstance(result, Mapping) else {})
    pitch_frames = [
        _normalize_frame(frame, index, metadata)
        for index, frame in enumerate(_extract_frames(result if isinstance(result, Mapping) else {}))
    ]

    note_events = _extract_events(result if isinstance(result, Mapping) else {}, "notes", "events")
    if not note_events:
        note_events = _extract_events(result if isinstance(result, Mapping) else {}, "note_events")

    chord_timeline = _extract_events(result if isinstance(result, Mapping) else {}, "chords", "timeline")
    key_trajectory = _extract_events(result if isinstance(result, Mapping) else {}, "keys", "trajectory")

    tessitura = {}
    tessitura_source = result.get("tessitura") if isinstance(result, Mapping) else None
    if isinstance(tessitura_source, Mapping):
        tessitura = {
            "metrics": _normalize_tessitura(tessitura_source.get("metrics") or tessitura_source),
            "pdf": tessitura_source.get("pdf"),
        }

    payload = {
        "metadata": metadata,
        "pitch_frames": pitch_frames,
        "note_events": [
            _normalize_event(event) for event in note_events
        ],
        "chord_timeline": [
            _normalize_event(event) for event in chord_timeline
        ],
        "key_trajectory": [
            _normalize_event(event) for event in key_trajectory
        ],
        "tessitura_metrics": tessitura.get("metrics", {}),
        "uncertainty_bounds": _normalize_uncertainty(result if isinstance(result, Mapping) else {}),
        "metadata_fields": {
            "analysis_version": metadata.get("analysis_version"),
            "source": metadata.get("source"),
        },
    }

    json_text = json.dumps(payload, indent=indent, sort_keys=True)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(json_text)
    return json_text


def generate_comparison_json_report(
    session_report: dict,
    output_path: str,
) -> str:
    """Write a comparison session report to a JSON file.

    Args:
        session_report: Dict from ``session_report_to_dict()`` or from the WS
            ``session_report`` message.
        output_path: Path to write the JSON file.

    Returns:
        The *output_path* string.
    """
    import json
    from pathlib import Path

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(session_report, fh, indent=2, default=str)
    return output_path


__all__ = ["generate_json_report"]
