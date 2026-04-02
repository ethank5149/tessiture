"""Visualization outputs for Phase 6.3 (matplotlib + optional plotly JSON).

Each function accepts the analysis result dictionary used by the CSV/JSON generators
and returns a matplotlib Figure or a serialized plotly-compatible JSON payload.
"""

from __future__ import annotations

import json
import math
from typing import Any, Mapping, MutableMapping, Optional, Sequence

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from reporting._helpers import (
    NOTE_NAMES,
    _safe_float,
    _ensure_mapping,
    _coerce_sequence,
    _first_float,
    _extract_frames,
    _extract_events,
)


def _frame_time(frame: Mapping[str, Any], index: int, metadata: Mapping[str, Any]) -> float:
    for key in ("time", "timestamp", "time_s", "t"):
        value = _safe_float(frame.get(key))
        if value is not None:
            return value
    frame_rate = _safe_float(metadata.get("frame_rate"))
    if frame_rate and frame_rate > 0:
        return float(index / frame_rate)
    sample_rate = _safe_float(metadata.get("sample_rate"))
    hop_length = _first_float(metadata, ("hop_length", "frame_hop"))
    if sample_rate and hop_length:
        return float(index * hop_length / sample_rate)
    return float(index)


def _hz_to_midi(frequency: float) -> Optional[float]:
    if frequency <= 0:
        return None
    return 69.0 + 12.0 * math.log2(frequency / 440.0)


def _midi_to_hz(midi: float) -> Optional[float]:
    return float(440.0 * (2.0 ** ((midi - 69.0) / 12.0)))


def _frame_f0(frame: Mapping[str, Any]) -> Optional[float]:
    for key in ("f0", "f0_hz", "frequency_hz", "frequency"):
        value = _safe_float(frame.get(key))
        if value is not None:
            return value
    midi_value = _first_float(frame, ("midi", "midi_value"))
    if midi_value is not None:
        return _midi_to_hz(midi_value)
    return None


def _frame_midi(frame: Mapping[str, Any]) -> Optional[float]:
    midi_value = _first_float(frame, ("midi", "midi_value"))
    if midi_value is not None:
        return midi_value
    f0 = _frame_f0(frame)
    if f0 is None:
        return None
    return _hz_to_midi(f0)


def _frame_confidence(frame: Mapping[str, Any]) -> Optional[float]:
    for key in ("confidence", "salience", "probability"):
        value = _safe_float(frame.get(key))
        if value is not None:
            return value
    return None


def _frame_uncertainty(frame: Mapping[str, Any]) -> Optional[float]:
    for key in ("uncertainty", "midi_uncertainty", "pitch_uncertainty"):
        value = _safe_float(frame.get(key))
        if value is not None:
            return value
    return None


def _note_name_to_midi(note: str) -> Optional[float]:
    if not isinstance(note, str) or not note:
        return None
    letter = note[0].upper()
    if letter not in "ABCDEFG":
        return None
    accidental = ""
    octave_str = note[1:]
    if len(note) > 1 and note[1] in ("#", "b"):
        accidental = note[1]
        octave_str = note[2:]
    if not octave_str or not octave_str.lstrip("-").isdigit():
        return None
    octave = int(octave_str)
    name = letter + ("#" if accidental == "#" else "" if accidental == "" else "b")
    if "b" in name:
        enharmonic = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
        name = enharmonic.get(name, name)
    if name not in NOTE_NAMES:
        return None
    note_index = NOTE_NAMES.index(name)
    return float((octave + 1) * 12 + note_index)


def _event_pitch(event: Mapping[str, Any]) -> Optional[float]:
    for key in ("midi", "midi_value", "pitch", "pitch_midi"):
        value = _safe_float(event.get(key))
        if value is not None:
            return value
    note = event.get("note") or event.get("label") or event.get("name")
    if isinstance(note, str):
        return _note_name_to_midi(note)
    return None


def _confidence_band(value: float, confidence: Optional[float], uncertainty: Optional[float], use_midi: bool) -> float:
    if uncertainty is not None and uncertainty > 0:
        return uncertainty
    base = 0.5 if use_midi else max(2.0, abs(value) * 0.02)
    if confidence is None:
        return base
    return base * (1.0 + (1.0 - max(0.0, min(1.0, confidence))))


def _empty_figure(title: str) -> Figure:
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.text(0.5, 0.5, "No data", ha="center", va="center")
    ax.set_title(title)
    ax.set_axis_off()
    return fig


def _empty_plotly(title: str) -> dict[str, Any]:
    return {
        "data": [],
        "layout": {
            "title": {"text": title},
            "annotations": [
                {"text": "No data", "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}
            ],
        },
    }


def plot_pitch_curve(
    result: Mapping[str, Any],
    *,
    window_start: Optional[float] = None,
    window_end: Optional[float] = None,
    use_midi: bool = False,
    backend: str = "matplotlib",
) -> Figure | dict[str, Any]:
    """Plot a scrolling pitch curve with confidence shading."""
    metadata = _ensure_mapping(result.get("metadata") if isinstance(result, Mapping) else {})
    frames = _extract_frames(result if isinstance(result, Mapping) else {})

    times: list[float] = []
    values: list[float] = []
    confidences: list[Optional[float]] = []
    uncertainties: list[Optional[float]] = []

    for idx, frame in enumerate(frames):
        time_value = _frame_time(frame, idx, metadata)
        if window_start is not None and time_value < window_start:
            continue
        if window_end is not None and time_value > window_end:
            continue
        pitch_value = _frame_midi(frame) if use_midi else _frame_f0(frame)
        if pitch_value is None:
            continue
        times.append(time_value)
        values.append(pitch_value)
        confidences.append(_frame_confidence(frame))
        uncertainties.append(_frame_uncertainty(frame))

    title = "Pitch Curve with Confidence"
    y_label = "MIDI" if use_midi else "Frequency (Hz)"

    if not times:
        return _empty_plotly(title) if backend == "plotly" else _empty_figure(title)

    lower: list[float] = []
    upper: list[float] = []
    for value, conf, uncert in zip(values, confidences, uncertainties):
        band = _confidence_band(value, conf, uncert, use_midi)
        lower.append(value - band)
        upper.append(value + band)

    if backend == "plotly":
        band_x = times + list(reversed(times))
        band_y = upper + list(reversed(lower))
        return {
            "data": [
                {
                    "type": "scatter",
                    "x": band_x,
                    "y": band_y,
                    "fill": "toself",
                    "fillcolor": "rgba(31,119,180,0.2)",
                    "line": {"color": "rgba(0,0,0,0)"},
                    "name": "Confidence band",
                    "hoverinfo": "skip",
                },
                {
                    "type": "scatter",
                    "x": times,
                    "y": values,
                    "mode": "lines",
                    "line": {"color": "#1f77b4"},
                    "name": "Pitch",
                },
            ],
            "layout": {
                "title": {"text": title},
                "xaxis": {"title": "Time (s)"},
                "yaxis": {"title": y_label},
            },
        }

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, values, color="tab:blue", linewidth=1.5, label="Pitch")
    ax.fill_between(times, lower, upper, color="tab:blue", alpha=0.2, label="Confidence band")
    ax.set_title(title)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel(y_label)
    if window_start is not None or window_end is not None:
        ax.set_xlim(left=window_start, right=window_end)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    return fig


def plot_piano_roll(
    result: Mapping[str, Any],
    *,
    backend: str = "matplotlib",
) -> Figure | dict[str, Any]:
    """Plot a piano roll with note events overlay and pitch curve."""
    metadata = _ensure_mapping(result.get("metadata") if isinstance(result, Mapping) else {})
    frames = _extract_frames(result if isinstance(result, Mapping) else {})
    events = _extract_events(result if isinstance(result, Mapping) else {}, "notes", "events")
    if not events:
        events = _extract_events(result if isinstance(result, Mapping) else {}, "note_events")

    title = "Piano Roll Overlay"

    if not events and not frames:
        return _empty_plotly(title) if backend == "plotly" else _empty_figure(title)

    note_events: list[dict[str, Any]] = []
    for event in events:
        start = _first_float(event, ("start", "time", "t"))
        end = _safe_float(event.get("end"))
        label = event.get("label") or event.get("note") or event.get("name")
        confidence = _first_float(event, ("confidence", "probability"))
        pitch = _event_pitch(event)
        if start is None or pitch is None:
            continue
        note_events.append(
            {
                "start": start,
                "end": end,
                "pitch": pitch,
                "label": label,
                "confidence": confidence,
            }
        )

    note_events.sort(key=lambda item: item["start"])
    for idx, event in enumerate(note_events):
        if event["end"] is None:
            next_start = note_events[idx + 1]["start"] if idx + 1 < len(note_events) else None
            event["end"] = (next_start if next_start is not None else event["start"] + 0.25)

    pitch_times: list[float] = []
    pitch_values: list[float] = []
    for idx, frame in enumerate(frames):
        pitch = _frame_midi(frame)
        if pitch is None:
            continue
        pitch_times.append(_frame_time(frame, idx, metadata))
        pitch_values.append(pitch)

    if backend == "plotly":
        shapes: list[dict[str, Any]] = []
        annotations: list[dict[str, Any]] = []
        for event in note_events:
            start = float(event["start"])
            end = float(event["end"]) if event["end"] is not None else start + 0.25
            pitch = float(event["pitch"])
            alpha = 0.3 + 0.5 * (event["confidence"] or 0.0)
            shapes.append(
                {
                    "type": "rect",
                    "x0": start,
                    "x1": end,
                    "y0": pitch - 0.3,
                    "y1": pitch + 0.3,
                    "fillcolor": f"rgba(44,160,44,{alpha:.2f})",
                    "line": {"color": "rgba(0,0,0,0)"},
                }
            )
            if event["label"]:
                annotations.append(
                    {
                        "x": (start + end) / 2.0,
                        "y": pitch + 0.45,
                        "text": str(event["label"]),
                        "showarrow": False,
                        "font": {"size": 9},
                    }
                )
        data = []
        if pitch_times:
            data.append(
                {
                    "type": "scatter",
                    "x": pitch_times,
                    "y": pitch_values,
                    "mode": "lines",
                    "line": {"color": "#1f77b4", "width": 1},
                    "name": "Pitch",
                }
            )
        return {
            "data": data,
            "layout": {
                "title": {"text": title},
                "xaxis": {"title": "Time (s)"},
                "yaxis": {"title": "MIDI"},
                "shapes": shapes,
                "annotations": annotations,
            },
        }

    fig, ax = plt.subplots(figsize=(10, 4))
    for event in note_events:
        start = float(event["start"])
        end = float(event["end"]) if event["end"] is not None else start + 0.25
        pitch = float(event["pitch"])
        alpha = 0.3 + 0.5 * (event["confidence"] or 0.0)
        rect = Rectangle((start, pitch - 0.3), end - start, 0.6, color="tab:green", alpha=alpha)
        ax.add_patch(rect)
        if event["label"]:
            ax.text((start + end) / 2.0, pitch + 0.45, str(event["label"]), ha="center", va="bottom", fontsize=8)

    if pitch_times:
        ax.plot(pitch_times, pitch_values, color="tab:blue", linewidth=1.0, alpha=0.8, label="Pitch")

    ax.set_title(title)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("MIDI")
    ax.grid(True, alpha=0.2)
    return fig


def _extract_tessitura_pdf(result: Mapping[str, Any]) -> tuple[list[float], list[float]]:
    tessitura = result.get("tessitura") if isinstance(result, Mapping) else None
    if not isinstance(tessitura, Mapping):
        return [], []
    pdf = tessitura.get("pdf") or tessitura.get("histogram") or tessitura.get("distribution")
    if isinstance(pdf, Mapping):
        x_values = _coerce_sequence(pdf.get("midi") or pdf.get("bins") or pdf.get("x"))
        y_values = _coerce_sequence(pdf.get("density") or pdf.get("weights") or pdf.get("y"))
        return [float(x) for x in x_values if _safe_float(x) is not None], [float(y) for y in y_values if _safe_float(y) is not None]
    if isinstance(pdf, Sequence) and not isinstance(pdf, (str, bytes)):
        x_values: list[float] = []
        y_values: list[float] = []
        for item in pdf:
            if isinstance(item, Mapping):
                x = _safe_float(item.get("midi") or item.get("x"))
                y = _safe_float(item.get("density") or item.get("y") or item.get("weight"))
                if x is not None and y is not None:
                    x_values.append(x)
                    y_values.append(y)
            elif isinstance(item, Sequence) and len(item) >= 2:
                x = _safe_float(item[0])
                y = _safe_float(item[1])
                if x is not None and y is not None:
                    x_values.append(x)
                    y_values.append(y)
        return x_values, y_values
    return [], []


def _histogram(values: Sequence[float], bin_size: float = 1.0) -> tuple[list[float], list[float]]:
    if not values:
        return [], []
    min_val = math.floor(min(values))
    max_val = math.ceil(max(values))
    if max_val <= min_val:
        return [min_val], [1.0]
    bins = int((max_val - min_val) / bin_size) + 1
    counts = [0.0 for _ in range(bins)]
    for value in values:
        index = int((value - min_val) / bin_size)
        index = max(0, min(index, bins - 1))
        counts[index] += 1.0
    total = sum(counts) or 1.0
    centers = [min_val + bin_size * (i + 0.5) for i in range(bins)]
    densities = [count / total for count in counts]
    return centers, densities


def plot_tessitura_heatmap(
    result: Mapping[str, Any],
    *,
    backend: str = "matplotlib",
) -> Figure | dict[str, Any]:
    """Plot a tessitura heatmap from the tessitura PDF or derived histogram."""
    x_values, y_values = _extract_tessitura_pdf(result)

    if not x_values or not y_values:
        frames = _extract_frames(result if isinstance(result, Mapping) else {})
        midi_values = [m for frame in frames if (m := _frame_midi(frame)) is not None]
        x_values, y_values = _histogram(midi_values)

    title = "Tessitura Heatmap"

    if not x_values or not y_values:
        return _empty_plotly(title) if backend == "plotly" else _empty_figure(title)

    if backend == "plotly":
        return {
            "data": [
                {
                    "type": "heatmap",
                    "x": x_values,
                    "y": [0],
                    "z": [y_values],
                    "colorscale": "Magma",
                    "colorbar": {"title": "Density"},
                }
            ],
            "layout": {
                "title": {"text": title},
                "xaxis": {"title": "MIDI"},
                "yaxis": {"showticklabels": False},
            },
        }

    fig, ax = plt.subplots(figsize=(10, 2.8))
    ax.imshow([y_values], aspect="auto", cmap="magma", extent=[min(x_values), max(x_values), 0, 1])
    ax.set_title(title)
    ax.set_xlabel("MIDI")
    ax.set_yticks([])
    fig.colorbar(ax.images[0], ax=ax, orientation="vertical", label="Density")
    return fig


def plot_chord_timeline(
    result: Mapping[str, Any],
    *,
    backend: str = "matplotlib",
) -> Figure | dict[str, Any]:
    """Plot the chord timeline as labeled segments."""
    events = _extract_events(result if isinstance(result, Mapping) else {}, "chords", "timeline")
    title = "Chord Timeline"

    if not events:
        return _empty_plotly(title) if backend == "plotly" else _empty_figure(title)

    timeline: list[dict[str, Any]] = []
    for event in events:
        start = _first_float(event, ("start", "time", "t"))
        end = _safe_float(event.get("end"))
        label = event.get("label") or event.get("chord") or event.get("name")
        if start is None:
            continue
        timeline.append({"start": start, "end": end, "label": label})

    timeline.sort(key=lambda item: item["start"])
    for idx, item in enumerate(timeline):
        if item["end"] is None:
            next_start = timeline[idx + 1]["start"] if idx + 1 < len(timeline) else None
            item["end"] = (next_start if next_start is not None else item["start"] + 0.5)

    if backend == "plotly":
        shapes: list[dict[str, Any]] = []
        annotations: list[dict[str, Any]] = []
        for item in timeline:
            start = float(item["start"])
            end = float(item["end"]) if item["end"] is not None else start + 0.5
            shapes.append(
                {
                    "type": "rect",
                    "x0": start,
                    "x1": end,
                    "y0": 0,
                    "y1": 1,
                    "fillcolor": "rgba(148,103,189,0.4)",
                    "line": {"color": "rgba(0,0,0,0)"},
                }
            )
            if item["label"]:
                annotations.append(
                    {
                        "x": (start + end) / 2.0,
                        "y": 0.5,
                        "text": str(item["label"]),
                        "showarrow": False,
                        "font": {"size": 10},
                    }
                )
        return {
            "data": [],
            "layout": {
                "title": {"text": title},
                "xaxis": {"title": "Time (s)"},
                "yaxis": {"showticklabels": False},
                "shapes": shapes,
                "annotations": annotations,
            },
        }

    fig, ax = plt.subplots(figsize=(10, 2.4))
    for item in timeline:
        start = float(item["start"])
        end = float(item["end"]) if item["end"] is not None else start + 0.5
        ax.broken_barh([(start, end - start)], (0, 1), facecolors="tab:purple", alpha=0.4)
        if item["label"]:
            ax.text((start + end) / 2.0, 0.5, str(item["label"]), ha="center", va="center", fontsize=9)

    ax.set_title(title)
    ax.set_xlabel("Time (s)")
    ax.set_yticks([])
    ax.set_ylim(0, 1)
    return fig


def plot_key_stability(
    result: Mapping[str, Any],
    *,
    backend: str = "matplotlib",
) -> Figure | dict[str, Any]:
    """Plot key stability as confidence over time."""
    events = _extract_events(result if isinstance(result, Mapping) else {}, "keys", "trajectory")
    title = "Key Stability"

    if not events:
        return _empty_plotly(title) if backend == "plotly" else _empty_figure(title)

    times: list[float] = []
    confidences: list[float] = []
    labels: list[Optional[str]] = []
    for event in events:
        start = _first_float(event, ("start", "time", "t"))
        end = _safe_float(event.get("end"))
        confidence = _first_float(event, ("confidence", "probability"))
        label = event.get("label") or event.get("key") or event.get("name")
        if start is None:
            continue
        midpoint = start if end is None else (start + end) / 2.0
        times.append(midpoint)
        confidences.append(confidence if confidence is not None else 0.0)
        labels.append(label if isinstance(label, str) else None)

    if backend == "plotly":
        annotations = []
        for time_value, conf_value, label in zip(times, confidences, labels):
            if label:
                annotations.append(
                    {
                        "x": time_value,
                        "y": conf_value + 0.03,
                        "text": label,
                        "showarrow": False,
                        "font": {"size": 9},
                    }
                )
        return {
            "data": [
                {
                    "type": "scatter",
                    "x": times,
                    "y": confidences,
                    "mode": "lines+markers",
                    "line": {"color": "#ff7f0e"},
                    "name": "Key confidence",
                }
            ],
            "layout": {
                "title": {"text": title},
                "xaxis": {"title": "Time (s)"},
                "yaxis": {"title": "Confidence", "range": [0, 1]},
                "annotations": annotations,
            },
        }

    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(times, confidences, color="tab:orange", marker="o", linewidth=1.5)
    for time_value, conf_value, label in zip(times, confidences, labels):
        if label:
            ax.text(time_value, conf_value + 0.03, label, rotation=25, ha="left", va="bottom", fontsize=8)
    ax.set_title(title)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Confidence")
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    return fig


def save_matplotlib_figure(figure: Figure, output_path: str, *, dpi: int = 150) -> None:
    """Save a matplotlib figure to disk."""
    figure.savefig(output_path, dpi=dpi, bbox_inches="tight")


def save_plotly_json(payload: Mapping[str, Any], output_path: str, *, indent: int = 2) -> str:
    """Serialize a plotly JSON payload and write it to disk."""
    text = json.dumps(payload, indent=indent, sort_keys=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text


__all__ = [
    "plot_pitch_curve",
    "plot_piano_roll",
    "plot_tessitura_heatmap",
    "plot_chord_timeline",
    "plot_key_stability",
    "save_matplotlib_figure",
    "save_plotly_json",
]
