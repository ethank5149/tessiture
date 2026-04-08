"""MIDI conversion helpers with calibration and uncertainty propagation.

Example:
    midi_vals, midi_sigma = convert_f0_to_midi(f0_hz)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import numpy as np


@dataclass
class MidiFrame:
    time_index: int
    frequency_hz: float
    frequency_uncertainty: float
    midi_value: float
    midi_uncertainty: float
    cents_deviation: float


def _frequency_to_midi(frequency_hz: float) -> float:
    if frequency_hz <= 0.0:
        return 0.0
    return float(69.0 + 12.0 * np.log2(frequency_hz / 440.0))


def _frequency_to_midi_uncertainty(frequency_hz: float, sigma_f: float) -> float:
    if frequency_hz <= 0.0:
        return 0.0
    return float((12.0 / np.log(2.0)) * (sigma_f / frequency_hz))


def combine_pitch_uncertainty(analytic_sigma: float, calibration_sigma: float) -> float:
    """Combine analytic and calibration uncertainty via quadrature."""
    analytic = max(float(analytic_sigma), 0.0)
    calibration = max(float(calibration_sigma), 0.0)
    return float(np.sqrt(analytic**2 + calibration**2))


def convert_f0_to_midi(
    f0_hz: np.ndarray,
    sigma_f: Optional[np.ndarray] = None,
    calibrate: Optional[Callable[[float], Tuple[float, float]]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert frequency array to MIDI values with uncertainty.

    Args:
        f0_hz: Array of fundamental frequencies.
        sigma_f: Optional per-frame frequency uncertainty.
        calibrate: Optional calibration hook returning (bias_hz, sigma_cal_hz).

    Returns:
        Tuple of (midi_values, midi_uncertainty).

    Example:
        midi_vals, midi_sigma = convert_f0_to_midi(f0_hz, sigma_f=sigma_f)
    """
    f0_hz = np.asarray(f0_hz, dtype=np.float32)
    sigma_f = np.zeros_like(f0_hz) if sigma_f is None else np.asarray(sigma_f, dtype=np.float32)

    voiced = f0_hz > 0.0

    if calibrate is not None:
        # Calibration path must iterate (callback is per-frame)
        corrected = np.zeros_like(f0_hz)
        sigma_total = np.zeros_like(f0_hz)
        for i, f0 in enumerate(f0_hz):
            if f0 <= 0.0:
                continue
            bias, sigma_cal = calibrate(float(f0))
            corrected[i] = f0 - float(bias)
            sigma_total[i] = combine_pitch_uncertainty(sigma_f[i], sigma_cal)
    else:
        # Fast vectorized path (no calibration — the common case)
        corrected = f0_hz.copy()
        sigma_total = sigma_f.copy()

    # Vectorized MIDI conversion: 69 + 12 * log2(f / 440)
    midi = np.zeros_like(corrected)
    safe = corrected > 0.0
    midi[safe] = 69.0 + 12.0 * np.log2(corrected[safe] / 440.0)

    # Vectorized uncertainty propagation: (12 / ln2) * (σ_f / f)
    midi_sigma = np.zeros_like(sigma_total)
    midi_sigma[safe] = (12.0 / np.log(2.0)) * (sigma_total[safe] / corrected[safe])

    return midi.astype(np.float32), midi_sigma.astype(np.float32)


def build_midi_frames(
    f0_hz: np.ndarray,
    sigma_f: Optional[np.ndarray] = None,
    calibrate: Optional[Callable[[float], Tuple[float, float]]] = None,
) -> list[MidiFrame]:
    """Construct MidiFrame entries from frequency and uncertainty arrays.

    Example:
        frames = build_midi_frames(f0_hz, sigma_f=sigma_f)
    """
    midi_vals, midi_sigma = convert_f0_to_midi(f0_hz, sigma_f=sigma_f, calibrate=calibrate)
    frames: list[MidiFrame] = []
    for i, f0 in enumerate(f0_hz):
        midi_val = float(midi_vals[i])
        midi_unc = float(midi_sigma[i])
        # Use explicit round-half-up (floor(x+0.5)) to avoid Python banker's rounding
        # at exactly ±50 cents from a note boundary
        nearest_midi = int(np.floor(midi_val + 0.5))
        cents_dev = (midi_val - nearest_midi) * 100.0 if f0 > 0.0 else 0.0
        frames.append(
            MidiFrame(
                time_index=i,
                frequency_hz=float(f0),
                frequency_uncertainty=float(0.0 if sigma_f is None else sigma_f[i]),
                midi_value=midi_val,
                midi_uncertainty=midi_unc,
                cents_deviation=float(cents_dev),
            )
        )
    return frames


__all__ = [
    "MidiFrame",
    "build_midi_frames",
    "combine_pitch_uncertainty",
    "convert_f0_to_midi",
]
