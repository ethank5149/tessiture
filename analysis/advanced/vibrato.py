"""Vibrato detection utilities for f0 trajectories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class VibratoFeatures:
    """Summary vibrato metrics derived from an f0 trajectory."""

    rate_hz: float
    depth_cents: float
    peak_power: float
    power_ratio: float
    start_index: int
    n_frames: int
    valid: bool


def _longest_voiced_segment(mask: np.ndarray) -> Tuple[int, int]:
    """Return (start, length) of the longest contiguous True segment."""

    best_start = 0
    best_len = 0
    current_start = 0
    current_len = 0
    for idx, is_voiced in enumerate(mask):
        if is_voiced:
            if current_len == 0:
                current_start = idx
            current_len += 1
        else:
            if current_len > best_len:
                best_start = current_start
                best_len = current_len
            current_len = 0
    if current_len > best_len:
        best_start = current_start
        best_len = current_len
    return best_start, best_len


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    kernel = np.ones(int(window), dtype=float)
    kernel /= float(np.sum(kernel))
    return np.convolve(values, kernel, mode="same")


def _deviation_cents(f0_hz: np.ndarray, reference_hz: float) -> np.ndarray:
    safe_ref = max(float(reference_hz), np.finfo(float).eps)
    return 1200.0 * np.log2(f0_hz / safe_ref)


def detect_vibrato(
    f0_hz: Sequence[float],
    sample_rate: int,
    hop_length: int,
    *,
    rate_range_hz: Tuple[float, float] = (3.0, 8.0),
    detrend_window_s: float = 0.25,
    min_frames: int = 24,
) -> VibratoFeatures:
    """Estimate vibrato rate (Hz) and depth (cents) from an f0 trajectory.

    Args:
        f0_hz: Sequence of fundamental frequency values in Hz (per frame).
        sample_rate: Audio sample rate in Hz.
        hop_length: Hop length in samples between f0 frames.
        rate_range_hz: (min, max) vibrato rate range to search in Hz.
        detrend_window_s: Window size in seconds for slow trend removal.
        min_frames: Minimum number of voiced frames required.
    """

    values = np.asarray(f0_hz, dtype=float)
    if values.size == 0:
        return VibratoFeatures(0.0, 0.0, 0.0, 0.0, 0, 0, False)

    voiced_mask = np.isfinite(values) & (values > 0.0)
    start, length = _longest_voiced_segment(voiced_mask)
    if length < max(int(min_frames), 3):
        return VibratoFeatures(0.0, 0.0, 0.0, 0.0, int(start), int(length), False)

    segment = values[start : start + length]
    reference_hz = float(np.median(segment))
    deviation = _deviation_cents(segment, reference_hz)

    frame_rate = float(sample_rate) / float(max(int(hop_length), 1))
    detrend_window = int(round(float(detrend_window_s) * frame_rate))
    detrend_window = max(detrend_window, 3)
    if detrend_window >= deviation.size:
        detrend_window = max(int(deviation.size // 2), 3)

    trend = _moving_average(deviation, detrend_window)
    residual = deviation - trend
    residual -= float(np.mean(residual))

    n = int(residual.size)
    if n < 3:
        return VibratoFeatures(0.0, 0.0, 0.0, 0.0, int(start), int(n), False)

    window = np.hanning(n) if n > 1 else np.ones(n, dtype=float)
    windowed = residual * window
    spectrum = np.fft.rfft(windowed)
    freqs = np.fft.rfftfreq(n, d=1.0 / frame_rate)

    min_rate, max_rate = rate_range_hz
    band_mask = (freqs >= float(min_rate)) & (freqs <= float(max_rate))
    if not np.any(band_mask):
        return VibratoFeatures(0.0, 0.0, 0.0, 0.0, int(start), int(n), False)

    band_indices = np.where(band_mask)[0]
    band_spectrum = spectrum[band_mask]
    magnitudes = np.abs(band_spectrum)
    peak_local = int(np.argmax(magnitudes))
    peak_index = int(band_indices[peak_local])
    peak_freq = float(freqs[peak_index])
    peak_mag = float(magnitudes[peak_local])

    window_sum = float(np.sum(window))
    amplitude = (2.0 * peak_mag) / max(window_sum, np.finfo(float).eps)
    power_spectrum = np.abs(spectrum) ** 2
    peak_power = float(power_spectrum[peak_index])
    band_power = float(np.sum(power_spectrum[band_mask]))
    power_ratio = peak_power / max(band_power, np.finfo(float).eps)

    return VibratoFeatures(
        rate_hz=peak_freq,
        depth_cents=abs(float(amplitude)),
        peak_power=peak_power,
        power_ratio=float(power_ratio),
        start_index=int(start),
        n_frames=int(n),
        valid=True,
    )


__all__ = ["VibratoFeatures", "detect_vibrato"]
