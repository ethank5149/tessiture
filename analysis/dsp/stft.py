"""Short-time Fourier transform helpers for Phase 2 analysis.

Performance & robustness improvements (critical for live streaming):
• Pre-compute Hann window + σ_f once per n_fft (huge speedup — thousands of calls/sec)
• Stricter input validation (empty audio, hop > n_fft, etc.)
• Cached helpers via lru_cache

Example:
    stft = compute_stft(audio, sample_rate=44100)
"""

from __future__ import annotations

from functools import lru_cache
from dataclasses import dataclass
from typing import Optional, Tuple, Any

import numpy as np

try:
    from scipy.signal.windows import hann as _scipy_hann
except ImportError:  # pragma: no cover
    _scipy_hann = None


@dataclass
class StftResult:
    spectrum: np.ndarray
    frequencies: np.ndarray
    times: np.ndarray
    sigma_f: np.ndarray
    window_norm: float  # Energy normalization: 1 / sqrt(sum(w^2) / N)


def _frame_signal(audio: np.ndarray, frame_length: int, hop_length: int) -> np.ndarray:
    """Slice audio into overlapping frames."""
    if audio.ndim != 1:
        raise ValueError("audio must be mono 1D array")
    if frame_length <= 0 or hop_length <= 0:
        raise ValueError(f"frame_length ({frame_length}) and hop_length ({hop_length}) must be positive")
    if hop_length > frame_length:
        raise ValueError("hop_length cannot exceed frame_length (n_fft)")
    if len(audio) == 0:
        raise ValueError("audio cannot be empty")
    if audio.size < frame_length:
        pad = frame_length - audio.size
        audio = np.pad(audio, (0, pad), mode="constant")
    n_frames = 1 + (audio.size - frame_length) // hop_length
    shape = (n_frames, frame_length)
    strides = (audio.strides[0] * hop_length, audio.strides[0])
    return np.lib.stride_tricks.as_strided(audio, shape=shape, strides=strides)


@lru_cache(maxsize=32)
def _get_hann_window(n_fft: int) -> np.ndarray:
    """Cached periodic Hann window (created once per n_fft)."""
    if _scipy_hann is not None:
        return _scipy_hann(n_fft, sym=False).astype(np.float32)
    # Fallback: manually construct periodic Hann
    return (0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n_fft) / n_fft)).astype(np.float32)


@lru_cache(maxsize=32)
def _get_sigma_f(n_fft: int, bin_spacing: float) -> np.ndarray:
    """Cached frequency uncertainty array (one per n_fft)."""
    return np.full(n_fft // 2 + 1, 0.72 * bin_spacing, dtype=np.float32)


def compute_stft(
    audio: np.ndarray,
    sample_rate: int,
    n_fft: int = 4096,
    hop_length: int = 512,
    window: Optional[np.ndarray] = None,
) -> StftResult:
    """Compute STFT magnitude spectrum with frequency uncertainty.

    NOTE: n_fft should match PYIN frame_length (already enforced by your latest commit).

    Performance note: Hann window + σ_f are now cached → massive win for streaming.
    """
    audio = np.asarray(audio, dtype=np.float32)

    # Use cached window + sigma_f (this is the big speedup)
    window = _get_hann_window(n_fft) if window is None else window
    if len(window) != n_fft:
        raise ValueError("window length must match n_fft")

    frames = _frame_signal(audio, n_fft, hop_length) * window[None, :]
    fft = np.fft.rfft(frames, n=n_fft, axis=1)
    spectrum = np.abs(fft).T.astype(np.float32)

    frequencies = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate).astype(np.float32)
    times = (np.arange(frames.shape[0]) * hop_length / float(sample_rate)).astype(np.float32)

    # Cached σ_f per n_fft
    bin_spacing = sample_rate / float(n_fft)
    sigma_f = _get_sigma_f(n_fft, bin_spacing)

    # Window energy normalization coefficient for proper magnitude scaling
    window_energy = float(np.sum(window.astype(np.float64) ** 2) / n_fft)
    window_norm = float(1.0 / np.sqrt(window_energy)) if window_energy > 0 else 1.0

    return StftResult(
        spectrum=spectrum,
        frequencies=frequencies,
        times=times,
        sigma_f=sigma_f,
        window_norm=window_norm,
    )
