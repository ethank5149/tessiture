"""Short-time Fourier transform helpers for Phase 2 analysis.

Example:
    stft = compute_stft(audio, sample_rate=44100)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class StftResult:
    spectrum: np.ndarray
    frequencies: np.ndarray
    times: np.ndarray
    sigma_f: np.ndarray


def _frame_signal(audio: np.ndarray, frame_length: int, hop_length: int) -> np.ndarray:
    """Slice audio into overlapping frames."""
    if audio.ndim != 1:
        raise ValueError("audio must be mono 1D array")
    if frame_length <= 0 or hop_length <= 0:
        raise ValueError("frame_length and hop_length must be positive")
    if audio.size < frame_length:
        pad = frame_length - audio.size
        audio = np.pad(audio, (0, pad), mode="constant")
    n_frames = 1 + (audio.size - frame_length) // hop_length
    shape = (n_frames, frame_length)
    strides = (audio.strides[0] * hop_length, audio.strides[0])
    return np.lib.stride_tricks.as_strided(audio, shape=shape, strides=strides)


def compute_stft(
    audio: np.ndarray,
    sample_rate: int,
    n_fft: int = 4096,
    hop_length: int = 512,
    window: Optional[np.ndarray] = None,
) -> StftResult:
    """Compute STFT magnitude spectrum with frequency uncertainty.

    Args:
        audio: Mono audio array.
        sample_rate: Sampling rate in Hz.
        n_fft: FFT window size.
        hop_length: Hop length in samples.
        window: Optional window array; if None, Hann window is used.

    Returns:
        StftResult with magnitude spectrum (freq x time), frequency grid, time grid, and σ_f.

    Example:
        stft = compute_stft(audio, sample_rate=44100, n_fft=2048, hop_length=256)
    """
    audio = np.asarray(audio, dtype=np.float32)
    if window is None:
        window = np.hanning(n_fft).astype(np.float32)
    if window.shape[0] != n_fft:
        raise ValueError("window length must match n_fft")

    frames = _frame_signal(audio, n_fft, hop_length) * window[None, :]
    fft = np.fft.rfft(frames, n=n_fft, axis=1)
    spectrum = np.abs(fft).T.astype(np.float32)

    frequencies = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate).astype(np.float32)
    times = (np.arange(frames.shape[0]) * hop_length / float(sample_rate)).astype(np.float32)

    # Frequency uncertainty σ_f approximated by bin spacing / sqrt(12)
    bin_spacing = sample_rate / float(n_fft)
    sigma_f = np.full_like(frequencies, bin_spacing / np.sqrt(12.0), dtype=np.float32)

    return StftResult(
        spectrum=spectrum,
        frequencies=frequencies,
        times=times,
        sigma_f=sigma_f,
    )
