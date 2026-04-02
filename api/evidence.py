"""
Evidence and chord timeline builders for the Tessiture API.

This module contains functions for building evidence payloads with event markers,
guidance recommendations, and chord detection timelines. These functions help
identify noteworthy moments in performances and provide actionable practice guidance.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from analysis.chords.detector import detect_chord
from api.pitch_utils import _midi_to_note_name
from api.serializers import _format_timestamp_label
from api.utils import _is_voiced_frame, _safe_float


def _build_evidence_payload(
    pitch_frames: Sequence[Mapping[str, Any]],
    *,
    note_events: Sequence[Mapping[str, Any]],
    duration_seconds: float,
) -> Dict[str, Any]:
    """Build additive evidence payload with low/high note references and guidance items."""
    evidence: Dict[str, Any] = {
        "events": [],
        "guidance": [],
        "lowest_voiced_note_ref": None,
        "highest_voiced_note_ref": None,
        "note_event_count": int(len(note_events)),
    }

    # Calculate seconds per frame for timestamp fallback
    seconds_per_frame = float(duration_seconds) / float(max(len(pitch_frames), 1))

    voiced_frames_data: List[Dict[str, float]] = []
    for idx, frame in enumerate(pitch_frames):
        if not isinstance(frame, Mapping) or not _is_voiced_frame(frame):
            continue

        time_s = _safe_float(frame.get("time"))
        if time_s is None:
            time_s = float(idx) * seconds_per_frame

        midi_value = _safe_float(frame.get("midi"))
        f0_hz = _safe_float(frame.get("f0_hz") or frame.get("f0"))
        if midi_value is None and f0_hz is not None and f0_hz > 0.0:
            midi_value = 69.0 + 12.0 * float(np.log2(f0_hz / 440.0))
        if midi_value is None:
            continue

        voiced_frames_data.append(
            {
                "time": float(max(time_s, 0.0)),
                "midi": float(midi_value),
                "f0_hz": float(f0_hz) if f0_hz is not None else 0.0,
                "confidence": float(_safe_float(frame.get("confidence")) or 0.0),
            }
        )

    if not voiced_frames_data:
        return evidence

    appended_events: List[Dict[str, Any]] = []

    def _add_event(event_id: str, label: str, timestamp_s: float, **extra: Any) -> Dict[str, Any]:
        safe_timestamp = float(max(_safe_float(timestamp_s) or 0.0, 0.0))
        payload: Dict[str, Any] = {
            "id": event_id,
            "label": label,
            "timestamp_s": safe_timestamp,
            "timestamp_label": _format_timestamp_label(safe_timestamp),
        }
        payload.update(extra)
        appended_events.append(payload)
        return payload

    lowest_frame = min(voiced_frames_data, key=lambda f: f["midi"])
    highest_frame = max(voiced_frames_data, key=lambda f: f["midi"])

    lowest_event = _add_event(
        "lowest_voiced_note",
        "Lowest voiced note",
        lowest_frame["time"],
        note=_midi_to_note_name(lowest_frame["midi"]),
        midi=lowest_frame["midi"],
        f0_hz=lowest_frame["f0_hz"],
        confidence=lowest_frame["confidence"],
    )
    highest_event = _add_event(
        "highest_voiced_note",
        "Highest voiced note",
        highest_frame["time"],
        note=_midi_to_note_name(highest_frame["midi"]),
        midi=highest_frame["midi"],
        f0_hz=highest_frame["f0_hz"],
        confidence=highest_frame["confidence"],
    )

    evidence["lowest_voiced_note_ref"] = lowest_event["id"]
    evidence["highest_voiced_note_ref"] = highest_event["id"]

    safe_duration = _safe_float(duration_seconds)
    if safe_duration is None or safe_duration <= 0.0:
        safe_duration = max(f["time"] for f in voiced_frames_data)
    safe_duration = max(float(safe_duration), 1e-6)

    segment_labels = ("Start", "Middle", "End")
    segment_stats: List[Dict[str, Any]] = [
        {"label": lbl, "count": 0, "weight": 0.0, "first_time": None}
        for lbl in segment_labels
    ]
    for vf in voiced_frames_data:
        normalized = float(np.clip(vf["time"] / safe_duration, 0.0, 0.999999))
        seg_idx = int(normalized * len(segment_labels))
        seg_idx = min(seg_idx, len(segment_labels) - 1)
        seg = segment_stats[seg_idx]
        seg["count"] += 1
        seg["weight"] += vf["confidence"] if vf["confidence"] > 0.0 else 1.0
        if seg["first_time"] is None:
            seg["first_time"] = vf["time"]

    peak_segment = max(segment_stats, key=lambda s: (s["count"], s["weight"]))
    peak_segment_event = _add_event(
        "segment_peak_voiced_activity",
        "Peak voiced activity segment",
        float(peak_segment["first_time"] if peak_segment["first_time"] is not None else 0.0),
        segment=peak_segment["label"],
        voiced_frame_count=int(peak_segment["count"]),
    )

    largest_jump_event: Optional[Dict[str, Any]] = None
    if len(voiced_frames_data) >= 2:
        ordered_frames = sorted(voiced_frames_data, key=lambda f: f["time"])
        best_jump: Optional[Dict[str, Any]] = None
        # Maximum inter-frame time gap to count as a single-phrase transition.
        # Gaps larger than this are phrase boundaries, not pitch jumps.
        max_intra_phrase_gap_s = 0.25
        for prev, curr in zip(ordered_frames, ordered_frames[1:]):
            time_gap = curr["time"] - prev["time"]
            if time_gap > max_intra_phrase_gap_s or time_gap <= 0.0:
                continue  # skip cross-phrase transitions
            jump_midi = abs(curr["midi"] - prev["midi"])
            if best_jump is None or jump_midi > float(best_jump["delta_midi"]):
                best_jump = {
                    "delta_midi": float(jump_midi),
                    "start_s": float(prev["time"]),
                    "end_s": float(curr["time"]),
                    "from_note": _midi_to_note_name(prev["midi"]),
                    "to_note": _midi_to_note_name(curr["midi"]),
                }
        if best_jump is not None:
            largest_jump_event = _add_event(
                "largest_pitch_jump",
                "Largest pitch jump",
                best_jump["end_s"],
                start_s=best_jump["start_s"],
                end_s=best_jump["end_s"],
                delta_midi=best_jump["delta_midi"],
                from_note=best_jump["from_note"],
                to_note=best_jump["to_note"],
            )

    evidence["events"] = appended_events

    event_by_id = {e["id"]: e for e in appended_events}

    evidence["guidance"].append(
        {
            "id": "guidance_range_edges",
            "claim": "Your lowest and highest voiced notes define the current edges of this take.",
            "why": (
                f"Lowest note {lowest_event.get('note')} appears near {lowest_event.get('timestamp_label')}, "
                f"and highest note {highest_event.get('note')} appears near {highest_event.get('timestamp_label')}."
            ),
            "action": "Jump to each edge and practice smooth, relaxed transitions into and out of those notes.",
            "evidence_refs": [lowest_event["id"], highest_event["id"]],
        }
    )

    evidence["guidance"].append(
        {
            "id": "guidance_peak_segment",
            "claim": "Most voiced activity is concentrated in one section of the recording.",
            "why": (
                f"The {peak_segment_event.get('segment', 'session')} segment contains the highest concentration "
                "of voiced frames."
            ),
            "action": "Start focused practice in that segment, then repeat once after a short recovery breath.",
            "evidence_refs": [peak_segment_event["id"]],
        }
    )

    if largest_jump_event is not None:
        evidence["guidance"].append(
            {
                "id": "guidance_large_transition_control",
                "claim": "One transition has the largest pitch jump and needs extra control.",
                "why": (
                    f"A jump of about {float(largest_jump_event.get('delta_midi') or 0.0):.1f} MIDI steps occurs near "
                    f"{largest_jump_event.get('timestamp_label')}."
                ),
                "action": "Loop this transition slowly before returning to full-tempo phrasing.",
                "evidence_refs": [largest_jump_event["id"]],
            }
        )

    return evidence


def _build_chord_timeline(note_events: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Build a chord timeline by detecting chords from simultaneously-sounding notes.

    Groups overlapping note events into time windows, then runs chord detection
    on each window's pitch set.  Single-note windows are labelled with the note
    name rather than a spurious chord label.
    """
    # --- collect valid events with start/end/midi --------------------------
    valid_events: List[Dict[str, Any]] = []
    for event in note_events:
        midi_value = _safe_float(event.get("midi"))
        start = _safe_float(event.get("start")) or 0.0
        end = _safe_float(event.get("end"))
        if midi_value is None:
            continue
        if end is None or end <= start:
            end = start + 0.1  # fallback duration
        valid_events.append({"start": start, "end": end, "midi": midi_value,
                             "note": event.get("note") or _midi_to_note_name(midi_value)})

    if not valid_events:
        return []

    # --- build boundary-point timeline -------------------------------------
    # Collect every unique start/end time as a boundary point, then for each
    # interval [boundary_i, boundary_{i+1}] find all notes sounding in that
    # interval.
    boundaries: List[float] = sorted({e["start"] for e in valid_events}
                                      | {e["end"] for e in valid_events})

    raw_timeline: List[Dict[str, Any]] = []
    for i in range(len(boundaries) - 1):
        seg_start = boundaries[i]
        seg_end = boundaries[i + 1]
        if seg_end <= seg_start:
            continue
        # Collect MIDI values of all notes sounding during this segment.
        sounding_midi: List[float] = []
        for ev in valid_events:
            if ev["start"] < seg_end and ev["end"] > seg_start:
                sounding_midi.append(ev["midi"])

        if not sounding_midi:
            continue

        if len(sounding_midi) >= 2:
            # Multiple simultaneous notes — run real chord detection.
            detected = detect_chord(sounding_midi, input_unit="midi", max_notes=4, top_k=3)
            label = detected.best_chord or "N.C."
            confidence = float(detected.probabilities.get(label, 0.0)) if detected.probabilities else 0.0
        else:
            # Single note — label with note name, not a chord.
            label = str(_midi_to_note_name(sounding_midi[0]))
            confidence = 0.0

        raw_timeline.append({"start": seg_start, "end": seg_end,
                             "label": label, "confidence": confidence})

    # --- merge adjacent segments with the same label -----------------------
    merged: List[Dict[str, Any]] = []
    for entry in raw_timeline:
        if merged and merged[-1]["label"] == entry["label"]:
            merged[-1]["end"] = entry["end"]
            # Keep the higher confidence of the two segments.
            merged[-1]["confidence"] = max(merged[-1]["confidence"], entry["confidence"])
        else:
            merged.append(dict(entry))

    return merged
