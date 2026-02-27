"""CSV export generator for analysis reporting (Phase 6.1).

Expected (flexible) analysis result schema:
    {
        "metadata": {
            "sample_rate": 44100,
            "hop_length": 512,
            "frame_rate": 86.13,
        },
        "pitch": {
            "frames": [
                {
                    "time": 0.0,
                    "f0_hz": 220.0,
                    "midi": 57.0,
                    "note": "A3",
                    "cents": -2.3,
                    "confidence": 0.82,
                },
                ...
            ]
        },
        "chords": {
            "timeline": [
                {"start": 0.0, "end": 1.5, "label": "Am", "confidence": 0.6},
                ...
            ]
        },
        "keys": {
            "trajectory": [
                {"start": 0.0, "end": 3.0, "label": "A minor", "confidence": 0.4},
                ...
            ]
        },
    }

Missing optional fields are handled gracefully; empty strings are emitted when data
is unavailable. The CSV columns are: time, f0, note, cents, confidence, chord, key.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import math
from io import StringIO
from typing import Any, Iterable, Mapping, Optional, Sequence


NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


@dataclass(frozen=True)
class _TimelineEvent:
    start: float
    end: Optional[float]
    label: Optional[str]


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


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    number = _safe_float(value)
    if number is None:
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:.6f}"


def _midi_to_note_name(midi_value: float) -> str:
    midi = _safe_float(midi_value)
    if midi is None:
        return ""
    note_index = int(round(midi)) % 12
    octave = int(round(midi)) // 12 - 1
    return f"{NOTE_NAMES[note_index]}{octave}"


def _midi_to_hz(midi_value: float) -> Optional[float]:
    midi = _safe_float(midi_value)
    if midi is None:
        return None
    return float(440.0 * (2.0 ** ((midi - 69.0) / 12.0)))


def _cents_from_midi(midi_value: float) -> Optional[float]:
    midi = _safe_float(midi_value)
    if midi is None:
        return None
    return float((midi - round(midi)) * 100.0)


def _extract_frames(result: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
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
            return current  # type: ignore[return-value]
    return []


def _extract_timeline(result: Mapping[str, Any], *path: str) -> list[_TimelineEvent]:
    current: Any = result
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return []
        current = current[key]
    if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
        return []
    events: list[_TimelineEvent] = []
    for item in current:
        if not isinstance(item, Mapping):
            continue
        start = _safe_float(item.get("start") or item.get("time") or item.get("t"))
        end = _safe_float(item.get("end"))
        label = item.get("label") or item.get("chord") or item.get("key") or item.get("name")
        events.append(_TimelineEvent(start=start if start is not None else 0.0, end=end, label=label))
    events.sort(key=lambda event: event.start)
    return events


def _select_label_at(time_value: float, events: Sequence[_TimelineEvent]) -> str:
    if not events:
        return ""
    for event in reversed(events):
        if time_value >= event.start and (event.end is None or time_value < event.end):
            return "" if event.label is None else str(event.label)
    return ""


def _frame_time(frame: Mapping[str, Any], index: int, metadata: Mapping[str, Any]) -> float:
    for key in ("time", "timestamp", "time_s", "t"):
        value = _safe_float(frame.get(key))
        if value is not None:
            return value
    frame_rate = _safe_float(metadata.get("frame_rate"))
    if frame_rate and frame_rate > 0:
        return float(index / frame_rate)
    sample_rate = _safe_float(metadata.get("sample_rate"))
    hop_length = _safe_float(metadata.get("hop_length") or metadata.get("frame_hop"))
    if sample_rate and hop_length:
        return float(index * hop_length / sample_rate)
    return float(index)


def _frame_f0(frame: Mapping[str, Any]) -> Optional[float]:
    for key in ("f0", "f0_hz", "frequency_hz", "frequency"):
        value = _safe_float(frame.get(key))
        if value is not None:
            return value
    midi_value = _safe_float(frame.get("midi") or frame.get("midi_value"))
    if midi_value is not None:
        return _midi_to_hz(midi_value)
    return None


def _frame_note(frame: Mapping[str, Any]) -> str:
    note = frame.get("note") or frame.get("note_name")
    if isinstance(note, str):
        return note
    midi_value = _safe_float(frame.get("midi") or frame.get("midi_value"))
    if midi_value is not None:
        return _midi_to_note_name(midi_value)
    return ""


def _frame_cents(frame: Mapping[str, Any]) -> Optional[float]:
    for key in ("cents", "cents_deviation"):
        value = _safe_float(frame.get(key))
        if value is not None:
            return value
    midi_value = _safe_float(frame.get("midi") or frame.get("midi_value"))
    if midi_value is not None:
        return _cents_from_midi(midi_value)
    return None


def _frame_confidence(frame: Mapping[str, Any]) -> Optional[float]:
    for key in ("confidence", "salience", "probability"):
        value = _safe_float(frame.get(key))
        if value is not None:
            return value
    return None


def generate_csv_report(result: Mapping[str, Any], output_path: Optional[str] = None) -> str:
    """Generate Phase 6.1 CSV export.

    Args:
        result: Analysis result dictionary (see module docstring for schema).
        output_path: Optional path to write the CSV to disk.

    Returns:
        CSV text with columns: time, f0, note, cents, confidence, chord, key.
    """
    metadata = result.get("metadata", {}) if isinstance(result, Mapping) else {}
    frames = _extract_frames(result if isinstance(result, Mapping) else {})
    chord_events = _extract_timeline(result if isinstance(result, Mapping) else {}, "chords", "timeline")
    key_events = _extract_timeline(result if isinstance(result, Mapping) else {}, "keys", "trajectory")

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["time", "f0", "note", "cents", "confidence", "chord", "key"])

    for idx, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            continue
        time_value = _frame_time(frame, idx, metadata)
        chord_label = _select_label_at(time_value, chord_events)
        key_label = _select_label_at(time_value, key_events)
        writer.writerow(
            [
                _format_value(time_value),
                _format_value(_frame_f0(frame)),
                _frame_note(frame),
                _format_value(_frame_cents(frame)),
                _format_value(_frame_confidence(frame)),
                chord_label,
                key_label,
            ]
        )

    csv_text = output.getvalue()
    if output_path:
        with open(output_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(csv_text)
    return csv_text


__all__ = ["generate_csv_report"]
