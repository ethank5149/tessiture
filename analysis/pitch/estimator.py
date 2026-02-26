"""Pitch estimation helpers (HPS, autocorrelation, salience).

Example:
    frames = estimate_pitch_frames(spectrum, frequencies, harmonic_frames)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from analysis.dsp.peak_detection import HarmonicFrame


@dataclass
class PitchFrame:
    time_index: int
    f0_hz: float
    salience: float
    components: Dict[str, float]


def harmonic_product_spectrum(
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    max_harmonics: int = 4,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute HPS for each frame.

    Args:
        spectrum: Magnitude spectrogram (freq x time).
        frequencies: Frequency grid.
        max_harmonics: Max harmonic multiplier for downsampling.

    Returns:
        hps_spectrum (freq x time) and frequency grid aligned to HPS bins.
    """
    spectrum = np.asarray(spectrum, dtype=np.float32)
    hps = spectrum.copy()
    for h in range(2, max_harmonics + 1):
        decimated = spectrum[::h, :]
        hps = hps[: decimated.shape[0], :] * decimated
    hps_freqs = frequencies[: hps.shape[0]]
    return hps, hps_freqs


def autocorrelation_pitch(
    audio_frame: np.ndarray,
    sample_rate: int,
    fmin: float = 80.0,
    fmax: float = 1200.0,
) -> float:
    """Estimate pitch using autocorrelation for a single frame."""
    frame = np.asarray(audio_frame, dtype=np.float32)
    frame -= np.mean(frame)
    if np.allclose(frame, 0.0):
        return 0.0
    corr = np.correlate(frame, frame, mode="full")[frame.size - 1 :]
    corr /= np.max(corr) + 1e-12
    min_lag = int(sample_rate / fmax)
    max_lag = int(sample_rate / fmin)
    if max_lag <= min_lag + 1:
        return 0.0
    search = corr[min_lag:max_lag]
    lag = int(np.argmax(search)) + min_lag
    if lag <= 0:
        return 0.0
    return float(sample_rate / lag)


def spectral_prominence(
    spectrum_frame: np.ndarray,
    frequencies: np.ndarray,
    f0: float,
    bandwidth: float = 10.0,
) -> float:
    """Score spectral prominence around f0."""
    if f0 <= 0.0:
        return 0.0
    freqs = np.asarray(frequencies, dtype=np.float32)
    mag = np.asarray(spectrum_frame, dtype=np.float32)
    mask = (freqs >= f0 - bandwidth) & (freqs <= f0 + bandwidth)
    if not np.any(mask):
        return 0.0
    return float(np.mean(mag[mask]) / (np.mean(mag) + 1e-12))


def _continuity_score(prev_f0: float, f0: float) -> float:
    if prev_f0 <= 0.0 or f0 <= 0.0:
        return 0.0
    ratio = max(prev_f0, f0) / min(prev_f0, f0)
    return float(np.exp(-abs(np.log(ratio)) * 2.0))


def estimate_pitch_frames(
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    harmonic_frames: List[HarmonicFrame],
    audio: Optional[np.ndarray] = None,
    sample_rate: int = 44100,
    hop_length: int = 512,
    weights: Optional[Dict[str, float]] = None,
) -> List[PitchFrame]:
    """Estimate pitch per frame using HPS, autocorrelation, and salience.

    Args:
        spectrum: Magnitude spectrogram (freq x time).
        frequencies: Frequency grid.
        harmonic_frames: Harmonic candidates per frame.
        audio: Optional mono audio array for autocorrelation.
        sample_rate: Sampling rate in Hz.
        hop_length: Hop length in samples for framing.
        weights: Optional weights for salience terms.

    Returns:
        List of PitchFrame objects.

    Example:
        frames = estimate_pitch_frames(spectrum, frequencies, harmonic_frames, audio=audio)
    """
    if weights is None:
        weights = {"H": 0.45, "C": 0.25, "V": 0.05, "S": 0.25}

    hps_spec, hps_freqs = harmonic_product_spectrum(spectrum, frequencies)
    frames: List[PitchFrame] = []
    prev_f0 = 0.0

    for t in range(spectrum.shape[1]):
        candidates = harmonic_frames[t].candidates if t < len(harmonic_frames) else []
        hps_frame = hps_spec[:, t]
        hps_idx = int(np.argmax(hps_frame)) if hps_frame.size else 0
        hps_f0 = float(hps_freqs[hps_idx]) if hps_frame.size else 0.0

        ac_f0 = 0.0
        if audio is not None:
            start = t * hop_length
            end = start + int(sample_rate * 0.05)
            frame_audio = audio[start:end] if end <= audio.size else audio[start:]
            if frame_audio.size > 0:
                ac_f0 = autocorrelation_pitch(frame_audio, sample_rate)

        best = None
        best_score = -np.inf
        for cand in candidates:
            f0 = cand.f0
            h_score = cand.score
            c_score = _continuity_score(prev_f0, f0)
            s_score = spectral_prominence(spectrum[:, t], frequencies, f0)
            v_score = 0.0  # placeholder for vibrato score
            score = (
                weights.get("H", 0.0) * h_score
                + weights.get("C", 0.0) * c_score
                + weights.get("V", 0.0) * v_score
                + weights.get("S", 0.0) * s_score
            )
            if score > best_score:
                best_score = score
                best = (f0, h_score, c_score, v_score, s_score)

        # Fallback to HPS or autocorrelation if no harmonic candidates
        if best is None:
            f0 = hps_f0 if hps_f0 > 0.0 else ac_f0
            h_score = float(np.max(hps_frame)) if hps_frame.size else 0.0
            c_score = _continuity_score(prev_f0, f0)
            v_score = 0.0
            s_score = spectral_prominence(spectrum[:, t], frequencies, f0)
            best_score = (
                weights.get("H", 0.0) * h_score
                + weights.get("C", 0.0) * c_score
                + weights.get("V", 0.0) * v_score
                + weights.get("S", 0.0) * s_score
            )
        else:
            f0, h_score, c_score, v_score, s_score = best

        components = {
            "H": float(h_score),
            "C": float(c_score),
            "V": float(v_score),
            "S": float(s_score),
            "HPS_f0": float(hps_f0),
            "AC_f0": float(ac_f0),
        }
        frames.append(PitchFrame(time_index=t, f0_hz=float(f0), salience=float(best_score), components=components))
        prev_f0 = float(f0)

    return frames
