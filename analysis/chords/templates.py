"""Chord template definitions for chord detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

NOTE_NAMES: Tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)


@dataclass(frozen=True)
class ChordTemplate:
    quality: str
    intervals: Tuple[int, ...]

    @property
    def size(self) -> int:
        return len(self.intervals)


CHORD_TEMPLATES: Dict[str, ChordTemplate] = {
    "maj": ChordTemplate("maj", (0, 4, 7)),
    "min": ChordTemplate("min", (0, 3, 7)),
    "dim": ChordTemplate("dim", (0, 3, 6)),
    "aug": ChordTemplate("aug", (0, 4, 8)),
    "7": ChordTemplate("7", (0, 4, 7, 10)),
    "maj7": ChordTemplate("maj7", (0, 4, 7, 11)),
    "min7": ChordTemplate("min7", (0, 3, 7, 10)),
}


def format_chord_name(root_pc: int, quality: str) -> str:
    """Format a chord name from a pitch-class root and quality."""
    root_pc = int(root_pc) % 12
    return f"{NOTE_NAMES[root_pc]}:{quality}"


def iter_templates(max_notes: int = 4) -> Iterable[ChordTemplate]:
    """Yield chord templates up to a maximum number of notes."""
    for template in CHORD_TEMPLATES.values():
        if template.size <= max_notes:
            yield template


def list_templates(max_notes: int = 4) -> List[ChordTemplate]:
    """Return chord templates up to a maximum number of notes."""
    return list(iter_templates(max_notes=max_notes))


__all__ = [
    "ChordTemplate",
    "CHORD_TEMPLATES",
    "NOTE_NAMES",
    "format_chord_name",
    "iter_templates",
    "list_templates",
]
