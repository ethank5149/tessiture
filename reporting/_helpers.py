"""Shared helper functions for the reporting package.

This module is the single canonical location for utility functions used
by pdf_composer.py, visualization.py, csv_generator.py, and json_generator.py.
Importing from here eliminates the duplication that previously existed
across multiple reporting modules.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, MutableMapping, Optional, Sequence


NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _safe_float(value: Any) -> Optional[float]:
    """Convert a value to a finite float, or return None."""
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _ensure_mapping(value: Any) -> MutableMapping[str, Any]:
    """Ensure a value is a mutable mapping, converting if necessary."""
    if isinstance(value, MutableMapping):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _coerce_sequence(value: Any) -> list[Any]:
    """Coerce a value to a list, returning empty list for non-sequences."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _first_float(mapping: Mapping[str, Any], keys: Sequence[str]) -> Optional[float]:
    """Return the first finite float found under any of the given keys."""
    for key in keys:
        if key not in mapping:
            continue
        value = _safe_float(mapping.get(key))
        if value is not None:
            return value
    return None


def _format_number(value: Any, *, decimals: int = 2) -> str:
    """Format a number for display, returning 'N/A' for None/non-finite."""
    number = _safe_float(value)
    if number is None:
        return "N/A"
    if number.is_integer():
        return str(int(number))
    return f"{number:.{decimals}f}"


def _format_band(value: Any) -> str:
    """Format a two-element range/band for display."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
        return f"{_format_number(value[0])} to {_format_number(value[1])}"
    return "N/A"


def _extract_frames(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Extract pitch frames from a result dict, searching multiple paths."""
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
    """Extract event list from a nested path in the result dict."""
    current: Any = result
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return []
        current = current[key]
    if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
        return [item for item in current if isinstance(item, Mapping)]
    return []
