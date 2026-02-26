"""Audio preprocessing helpers for Phase 2 analysis.

Example:
    result = preprocess_audio(audio, sample_rate=48000)
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd
from typing import Dict, Tuple

import numpy as np

try:  # Optional dependency
    from scipy import signal as _signal
except Exception:  # pragma: no cover - optional
    _signal = None


@dataclass
class PreprocessResult:
    audio: np.ndarray
    sample_rate: int
    info: Dict[str, float]


def _to_float(audio: np.ndarray) -> np.ndarray:
    """Convert audio to float32 in [-1, 1] where possible."""
    if np.issubdtype(audio.dtype, np.floating):
        return audio.astype(np.float32, copy=False)
    if np.issubdtype(audio.dtype, np.integer):
        info = np.iinfo(audio.dtype)
        scale = max(abs(info.min), info.max)
        return (audio.astype(np.float32) / float(scale)).astype(np.float32)
    return audio.astype(np.float32)


def _to_mono(audio: np.ndarray) -> np.ndarray:
    """Average multi-channel audio to mono."""
    if audio.ndim == 1:
        return audio
    if audio.ndim != 2:
        raise ValueError("audio must be 1D or 2D array")
    # Heuristic: if first dimension is small, treat as channels-first
    if audio.shape[0] <= 8:
        return np.mean(audio, axis=0)
    return np.mean(audio, axis=1)


def _normalize(audio: np.ndarray, peak: float = 0.99, eps: float = 1e-12) -> Tuple[np.ndarray, float, float]:
    """Normalize audio to target peak, returning pre/post peaks."""
    peak_before = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak_before <= eps:
        return audio, peak_before, peak_before
    scale = min(peak / peak_before, 1.0)
    normalized = audio * scale
    peak_after = float(np.max(np.abs(normalized))) if normalized.size else 0.0
    return normalized, peak_before, peak_after


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> Tuple[np.ndarray, bool]:
    """Resample audio to target sample rate."""
    if orig_sr == target_sr:
        return audio, False
    if _signal is not None:
        g = gcd(orig_sr, target_sr)
        up = target_sr // g
        down = orig_sr // g
        resampled = _signal.resample_poly(audio, up, down).astype(np.float32)
        return resampled, True
    # Fallback: linear interpolation
    ratio = target_sr / float(orig_sr)
    new_len = int(round(audio.shape[-1] * ratio))
    if new_len <= 1:
        return audio, False
    x_old = np.linspace(0.0, 1.0, audio.shape[-1], endpoint=False)
    x_new = np.linspace(0.0, 1.0, new_len, endpoint=False)
    resampled = np.interp(x_new, x_old, audio).astype(np.float32)
    return resampled, True


def preprocess_audio(
    audio: np.ndarray,
    sample_rate: int,
    target_sr: int = 44100,
    mono: bool = True,
    normalize: bool = True,
    peak: float = 0.99,
) -> PreprocessResult:
    """Preprocess audio by converting to mono, resampling, and normalizing.

    Args:
        audio: Input audio array (mono or multi-channel).
        sample_rate: Original sampling rate in Hz.
        target_sr: Desired sampling rate in Hz.
        mono: If True, downmix to mono.
        normalize: If True, normalize to target peak.
        peak: Target peak amplitude for normalization.

    Returns:
        PreprocessResult containing processed audio, target sample rate, and metadata.

    Example:
        result = preprocess_audio(audio, sample_rate=48000, target_sr=44100)
    """
    audio = _to_float(np.asarray(audio))
    original_shape = tuple(audio.shape)
    if mono:
        audio = _to_mono(audio)

    audio, did_resample = _resample(audio, sample_rate, target_sr)

    peak_before = float(np.max(np.abs(audio))) if audio.size else 0.0
    if normalize:
        audio, peak_before, peak_after = _normalize(audio, peak=peak)
    else:
        peak_after = peak_before

    info = {
        "original_sample_rate": float(sample_rate),
        "target_sample_rate": float(target_sr),
        "resampled": float(did_resample),
        "original_shape_0": float(original_shape[0]) if original_shape else 0.0,
        "peak_before": float(peak_before),
        "peak_after": float(peak_after),
    }
    return PreprocessResult(audio=audio.astype(np.float32), sample_rate=target_sr, info=info)
