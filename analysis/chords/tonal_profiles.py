"""Tonal profile definitions for key detection."""

from __future__ import annotations

from typing import Dict, Iterable, Tuple

import numpy as np

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

# Krumhansl-Schmuckler tonal profiles (major/minor).
KRUMHANSL_MAJOR: np.ndarray = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float64,
)

KRUMHANSL_MINOR: np.ndarray = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float64,
)


def rotate_profile(profile: np.ndarray, root_pc: int) -> np.ndarray:
    """Rotate a tonal profile to a pitch-class root."""
    root_pc = int(root_pc) % 12
    return np.roll(np.asarray(profile, dtype=np.float64), root_pc)


def build_tonal_profile_map(
    *,
    major_profile: np.ndarray = KRUMHANSL_MAJOR,
    minor_profile: np.ndarray = KRUMHANSL_MINOR,
) -> Dict[str, np.ndarray]:
    """Build a mapping of key labels to rotated tonal profiles."""
    profiles: Dict[str, np.ndarray] = {}
    for root in range(12):
        profiles[f"{NOTE_NAMES[root]}:maj"] = rotate_profile(major_profile, root)
        profiles[f"{NOTE_NAMES[root]}:min"] = rotate_profile(minor_profile, root)
    return profiles


def iter_key_labels() -> Iterable[str]:
    """Yield canonical key labels in major/minor order."""
    for root in range(12):
        yield f"{NOTE_NAMES[root]}:maj"
    for root in range(12):
        yield f"{NOTE_NAMES[root]}:min"


__all__ = [
    "KRUMHANSL_MAJOR",
    "KRUMHANSL_MINOR",
    "NOTE_NAMES",
    "build_tonal_profile_map",
    "iter_key_labels",
    "rotate_profile",
]