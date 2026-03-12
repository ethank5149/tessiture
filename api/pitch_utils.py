"""Pitch and note conversion utilities for the Tessiture API.

This module contains functions for converting between MIDI values,
frequencies (Hz), and note names, as well as building pitch payloads
and note events.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from api import config
from api.utils import _safe_float


def _midi_to_note_name(midi_value: float) -> str:
    """Convert a MIDI note number to a note name.
    
    Args:
        midi_value: MIDI note.g., 60 number (e = C4).
        
    Returns:
        Note name with octave (e.g., "C4", "F#5").
    """
    rounded = int(round(float(midi_value)))
    note_index = rounded % 12
    octave = rounded // 12 - 1
    return f"{config.NOTE_NAMES[note_index]}{octave}"


def _hz_to_note_name(frequency_hz: Any) -> Optional[str]:
    """Convert a frequency in Hz to a note name.
    
    Args:
        frequency_hz: Frequency in Hz.
        
    Returns:
        Note name with octave, or None if invalid.
    """
    frequency = _safe_float(frequency_hz)
    if frequency is None or frequency <= 0.0:
        return None
    midi_value = 69.0 + 12.0 * float(np.log2(frequency / 440.0))
    return _midi_to_note_name(midi_value)


def _unit_supports_pitch_note_names(unit: Any) -> bool:
    """Check if a unit supports pitch note name annotations.
    
    Args:
        unit: The unit string to check.
        
    Returns:
        True if the unit is Hz or MIDI.
    """
    return str(unit or "").strip().upper() in {"HZ", "MIDI"}


def _pitch_value_to_note_name(value: Any, unit: Any) -> Optional[str]:
    """Convert a pitch value to a note name based on unit.
    
    Args:
        value: The pitch value.
        unit: The unit (Hz or MIDI).
        
    Returns:
        Note name, or None if conversion not possible.
    """
    unit_upper = str(unit or "").strip().upper()
    if unit_upper == "MIDI":
        midi_value = _safe_float(value)
        return _midi_to_note_name(midi_value) if midi_value is not None else None
    if unit_upper == "HZ":
        return _hz_to_note_name(value)
    return None


def _midi_values_to_note_names(values: Sequence[Any]) -> List[Optional[str]]:
    """Convert a sequence of MIDI values to note names.
    
    Args:
        values: Sequence of MIDI values.
        
    Returns:
        List of note names (None for invalid values).
    """
    notes: List[Optional[str]] = []
    for value in values:
        midi_value = _safe_float(value)
        notes.append(_midi_to_note_name(midi_value) if midi_value is not None else None)
    return notes


def _normalize_analysis_diagnostics(payload: Any) -> Optional[Dict[str, Any]]:
    """Normalize analysis diagnostics from raw payload.
    
    Args:
        payload: Raw diagnostics payload.
        
    Returns:
        Normalized diagnostics dictionary.
    """
    if not isinstance(payload, Mapping):
        return None

    attempted_raw = payload.get("attempted_methods")
    attempted_methods = (
        [str(item) for item in attempted_raw if isinstance(item, (str, int, float))]
        if isinstance(attempted_raw, Sequence) and not isinstance(attempted_raw, (str, bytes))
        else []
    )

    strategy_path = payload.get("strategy_path")
    fallback_reason = payload.get("fallback_reason")

    return {
        "primary_method_used": str(payload.get("primary_method_used") or "unknown"),
        "attempted_methods": attempted_methods,
        "strategy_path": str(strategy_path) if strategy_path is not None else None,
        "fallback_reason": str(fallback_reason) if fallback_reason is not None else None,
    }


def _extract_pitch_frame_diagnostics(
    pitch_candidates: Sequence[Any],
) -> List[Optional[Dict[str, Any]]]:
    """Extract diagnostics from pitch frame candidates.
    
    Args:
        pitch_candidates: Sequence of pitch frame candidates.
        
    Returns:
        List of normalized diagnostics.
    """
    diagnostics: List[Optional[Dict[str, Any]]] = []
    for frame in pitch_candidates:
        components = getattr(frame, "components", None)
        diag_payload = components.get("analysis_diagnostics") if isinstance(components, Mapping) else None
        diagnostics.append(_normalize_analysis_diagnostics(diag_payload))
    return diagnostics


def _summarize_pitch_method_diagnostics(
    frame_diagnostics: Sequence[Optional[Mapping[str, Any]]],
) -> Dict[str, Any]:
    """Summarize pitch method diagnostics across all frames.
    
    Args:
        frame_diagnostics: Sequence of frame diagnostics.
        
    Returns:
        Summary dictionary.
    """
    method_counts: Dict[str, int] = {}
    fallback_reasons: Dict[str, int] = {}
    attempted_methods: List[str] = []
    strategy_path: Optional[str] = None

    for diag in frame_diagnostics:
        if not isinstance(diag, Mapping):
            continue

        method = str(diag.get("primary_method_used") or "unknown")
        method_counts[method] = method_counts.get(method, 0) + 1

        fallback_reason = diag.get("fallback_reason")
        if fallback_reason:
            reason = str(fallback_reason)
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1

        if not attempted_methods:
            attempted = diag.get("attempted_methods")
            if isinstance(attempted, Sequence) and not isinstance(attempted, (str, bytes)):
                attempted_methods = [str(item) for item in attempted if isinstance(item, (str, int, float))]

        if strategy_path is None:
            strategy = diag.get("strategy_path")
            if strategy is not None:
                strategy_path = str(strategy)

    primary_method_used = max(method_counts, key=method_counts.get) if method_counts else None
    fallback_reason = max(fallback_reasons, key=fallback_reasons.get) if fallback_reasons else None

    return {
        "primary_method_used": primary_method_used,
        "attempted_methods": attempted_methods,
        "strategy_path": strategy_path,
        "fallback_reason": fallback_reason,
        "method_counts": method_counts,
        "fallback_reasons": fallback_reasons,
        "frames_with_diagnostics": int(sum(1 for diag in frame_diagnostics if isinstance(diag, Mapping))),
    }


def _build_pitch_payload(
    f0_hz: np.ndarray,
    salience: np.ndarray,
    midi_values: np.ndarray,
    midi_sigma: np.ndarray,
    *,
    sample_rate: int,
    hop_length: int,
    frame_diagnostics: Optional[Sequence[Optional[Mapping[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Build a pitch payload from analysis results.
    
    Args:
        f0_hz: Array of f0 values in Hz.
        salience: Array of salience values.
        midi_values: Array of MIDI values.
        midi_sigma: Array of MIDI uncertainty values.
        sample_rate: Audio sample rate.
        hop_length: STFT hop length.
        frame_diagnostics: Optional per-frame diagnostics.
        
    Returns:
        List of frame dictionaries.
    """
    f0_values = np.asarray(f0_hz, dtype=float)
    salience_values = np.asarray(salience, dtype=float)
    midi = np.asarray(midi_values, dtype=float)
    midi_uncertainty = np.asarray(midi_sigma, dtype=float)

    frame_count = int(max(f0_values.size, salience_values.size, midi.size, midi_uncertainty.size))
    frames: List[Dict[str, Any]] = []
    seconds_per_frame = float(hop_length) / float(max(sample_rate, 1))

    for idx in range(frame_count):
        f0_value = _safe_float(f0_values[idx] if idx < f0_values.size else None)
        salience_value = _safe_float(salience_values[idx] if idx < salience_values.size else None)
        midi_value = _safe_float(midi[idx] if idx < midi.size else None)
        uncertainty_value = _safe_float(midi_uncertainty[idx] if idx < midi_uncertainty.size else None)

        if midi_value is not None and midi_value <= 0.0:
            midi_value = None

        confidence = float(np.clip(salience_value if salience_value is not None else 0.0, 0.0, 1.0))
        cents = float((midi_value - round(midi_value)) * 100.0) if midi_value is not None else None
        note_name = _midi_to_note_name(midi_value) if midi_value is not None else None

        frame_payload: Dict[str, Any] = {
            "index": idx,
            "time": float(idx) * seconds_per_frame,
            "f0_hz": f0_value,
            "f0": f0_value,
            "midi": midi_value,
            "note": note_name,
            "note_name": note_name,
            "cents": cents,
            "confidence": confidence,
            "uncertainty": float(max(uncertainty_value, 0.0)) if uncertainty_value is not None else 0.0,
            "salience": salience_value,
        }
        if frame_diagnostics is not None and idx < len(frame_diagnostics):
            normalized_diag = _normalize_analysis_diagnostics(frame_diagnostics[idx])
            if normalized_diag is not None:
                frame_payload["analysis_diagnostics"] = normalized_diag

        frames.append(frame_payload)

    return frames


def _build_note_events(frames: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Build note events from pitch frames with lookback-based note splitting.
    
    Uses lookback averaging and hysteresis-based splitting logic to segment
    contiguous voiced frames into discrete musical note events. This is the
    production implementation with improved note transition detection.
    
    Args:
        frames: Sequence of pitch frames with midi, time, and confidence fields.
        
    Returns:
        List of note events with start/end times, midi pitch, and confidence.
    """
    events: List[Dict[str, Any]] = []
    start_idx: Optional[int] = None
    active_values: List[float] = []
    active_confidence: List[float] = []
    min_event_frames = max(int(config.NOTE_EVENT_MIN_FRAMES), 1)

    def _reset_active() -> None:
        nonlocal start_idx, active_values, active_confidence
        start_idx = None
        active_values = []
        active_confidence = []

    def _close_event(end_idx: int) -> None:
        if start_idx is None or not active_values:
            _reset_active()
            return

        start_time = _safe_float(frames[start_idx].get("time")) or 0.0
        end_time = _safe_float(frames[end_idx].get("time")) or start_time
        midi_mean = float(np.mean(np.asarray(active_values, dtype=float)))
        confidence = (
            float(np.mean(np.asarray(active_confidence, dtype=float))) if active_confidence else 0.0
        )
        events.append(
            {
                "start": float(start_time),
                "end": float(end_time),
                "duration": float(max(end_time - start_time, 0.0)),
                "pitch": midi_mean,
                "midi": midi_mean,
                "note": _midi_to_note_name(midi_mean),
                "note_name": _midi_to_note_name(midi_mean),
                "confidence": confidence,
            }
        )
        _reset_active()

    for idx, frame in enumerate(frames):
        midi_value = _safe_float(frame.get("midi"))
        confidence_value = _safe_float(frame.get("confidence")) or 0.0

        if midi_value is None or confidence_value < config.NOTE_EVENT_MIN_CONFIDENCE:
            if start_idx is not None:
                _close_event(idx - 1)
            continue

        if start_idx is None:
            start_idx = idx
            active_values.append(midi_value)
            active_confidence.append(confidence_value)
            continue

        # Use lookback averaging for more stable note transition detection
        lookback_count = min(len(active_values), min_event_frames)
        active_center = float(np.mean(np.asarray(active_values[-lookback_count:], dtype=float)))
        active_note = int(round(active_center))
        current_note = int(round(midi_value))
        should_split = (
            current_note != active_note
            and abs(midi_value - active_center) >= config.NOTE_EVENT_SPLIT_HYSTERESIS_MIDI
            and len(active_values) >= min_event_frames
        )

        if should_split:
            _close_event(idx - 1)
            start_idx = idx
            active_values.append(midi_value)
            active_confidence.append(confidence_value)
            continue

        active_values.append(midi_value)
        active_confidence.append(confidence_value)

    if start_idx is not None:
        _close_event(len(frames) - 1)

    return events


def _build_example_payload(example: Mapping[str, Any], file_path: Any) -> Dict[str, Any]:
    """Build an example payload dictionary.
    
    Args:
        example: The example metadata.
        file_path: Path to the example file.
        
    Returns:
        Formatted example payload.
    """
    from api.utils import _build_example_payload as _utils_build_example_payload
    return _utils_build_example_payload(example, file_path)


def _slugify_example_id(file_path: Any) -> str:
    """Convert a file path to a slugified example ID.
    
    Args:
        file_path: Path to the example file.
        
    Returns:
        Slugified example ID.
    """
    from api.utils import _slugify_example_id as _utils_slugify_example_id
    return _utils_slugify_example_id(file_path)


def _guess_example_content_type(file_path: Any) -> str:
    """Guess the content type of an example file.
    
    Args:
        file_path: Path to the example file.
        
    Returns:
        Guessed content type.
    """
    from api.utils import _guess_example_content_type as _utils_guess_content_type
    return _utils_guess_content_type(file_path)


def _parse_example_stem(stem: str) -> Dict[str, Optional[str]]:
    """Parse artist, optional album, and title from an example filename stem.
    
    Args:
        stem: The filename stem to parse.
        
    Returns:
        Dictionary with artist, album, and title.
    """
    from api.utils import _parse_example_stem as _utils_parse_example_stem
    return _utils_parse_example_stem(stem)


def _discover_example_tracks() -> List[tuple[Dict[str, Any], Any]]:
    """Discover all available example tracks in the examples directory.
    
    Returns:
        List of tuples containing example metadata and file path.
    """
    from api.utils import _discover_example_tracks as _utils_discover_tracks
    return _utils_discover_tracks()


def _list_available_example_tracks() -> List[Dict[str, Any]]:
    """List all available example tracks.
    
    Returns:
        List of example track metadata.
    """
    from api.utils import _list_available_example_tracks as _utils_list_tracks
    return _utils_list_tracks()


def _resolve_example_track(example_id: str) -> tuple[Dict[str, Any], Any]:
    """Resolve an example track by its ID.
    
    Args:
        example_id: The example track ID.
        
    Returns:
        Tuple of example metadata and file path.
    """
    from api.utils import _resolve_example_track as _utils_resolve_track
    return _utils_resolve_track(example_id)
