"""Pitch estimation helpers (HPS, autocorrelation, salience).

Example:
    frames = estimate_pitch_frames(spectrum, frequencies, harmonic_frames)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from analysis.dsp.peak_detection import HarmonicFrame


@dataclass
class PitchFrame:
    time_index: int
    f0_hz: float
    salience: float
    components: Dict[str, Any]


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
    # Use log2 ratio to measure pitch distance
    log2_ratio = abs(np.log2(max(prev_f0, f0) / min(prev_f0, f0)))
    # Penalize deviation from nearest octave (octave errors are common in pitch tracking)
    nearest_octave = round(log2_ratio)
    octave_residual = abs(log2_ratio - nearest_octave)
    # Strong penalty for non-octave deviations; light penalty for octave jumps
    return float(np.exp(-octave_residual * 4.0))


def compute_voicing_mask(
    pitch_frames: List[PitchFrame],
    salience_threshold: float = 0.15,
    min_f0_hz: float = 60.0,
    max_f0_hz: float = 1600.0,
) -> List[bool]:
    """Determine which pitch frames represent voiced segments.

    A frame is considered voiced if:
    1. Its f0 is within the specified range [min_f0_hz, max_f0_hz]
    2. Its salience exceeds the threshold

    Args:
        pitch_frames: List of PitchFrame objects.
        salience_threshold: Minimum salience to be considered voiced.
        min_f0_hz: Minimum fundamental frequency for voiced frames.
        max_f0_hz: Maximum fundamental frequency for voiced frames.

    Returns:
        List of booleans, True if the frame is voiced.
    """
    voiced = []
    for frame in pitch_frames:
        is_voiced = (
            frame.f0_hz >= min_f0_hz
            and frame.f0_hz <= max_f0_hz
            and frame.salience >= salience_threshold
        )
        voiced.append(is_voiced)
    return voiced


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
        weights: Optional weights for salience terms. Accepts keys "H", "C", "S"
            (and optionally "V" for backward compatibility, but V is not used).

    Returns:
        List of PitchFrame objects.

    Example:
        frames = estimate_pitch_frames(spectrum, frequencies, harmonic_frames, audio=audio)
    """
    if weights is None:
        weights = {"H": 0.474, "C": 0.263, "S": 0.263}

    hps_spec, hps_freqs = harmonic_product_spectrum(spectrum, frequencies)
    frames: List[PitchFrame] = []
    prev_f0 = 0.0

    for t in range(spectrum.shape[1]):
        candidates = harmonic_frames[t].candidates if t < len(harmonic_frames) else []
        hps_frame = hps_spec[:, t]
        hps_idx = int(np.argmax(hps_frame)) if hps_frame.size else 0
        hps_f0 = float(hps_freqs[hps_idx]) if hps_frame.size else 0.0
        attempted_methods = [
            "harmonic_candidates",
            "hps_peak_ratio_gate",
            "autocorrelation",
        ]
        strategy_path = "harmonic_candidates -> hps_peak_ratio_gate -> autocorrelation"

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
            score = (
                weights.get("H", 0.0) * h_score
                + weights.get("C", 0.0) * c_score
                + weights.get("S", 0.0) * s_score
            )
            if score > best_score:
                best_score = score
                best = (f0, h_score, c_score, s_score)

        # Fallback to HPS or autocorrelation if no harmonic candidates
        if best is None:
            # Only use HPS f0 if it shows clear harmonic dominance over noise floor
            if hps_f0 > 0.0 and hps_frame.size > 0:
                hps_peak = float(np.max(hps_frame))
                hps_median = float(np.median(hps_frame))
                hps_voiced = hps_median > 0.0 and (hps_peak / hps_median) >= 5.0
            else:
                hps_voiced = False
            if hps_voiced and hps_f0 > 0.0:
                f0 = hps_f0
                method_used = "hps_fallback"
                fallback_reason: Optional[str] = "no_harmonic_candidates"
            else:
                f0 = ac_f0
                if ac_f0 > 0.0:
                    method_used = "autocorrelation_fallback"
                    fallback_reason = "no_harmonic_candidates_and_hps_not_voiced"
                else:
                    method_used = "no_pitch_detected"
                    fallback_reason = "no_harmonic_candidates_and_no_viable_fallback"
            h_score = float(np.max(hps_frame)) if hps_frame.size else 0.0
            c_score = _continuity_score(prev_f0, f0)
            s_score = spectral_prominence(spectrum[:, t], frequencies, f0)
            best_score = (
                weights.get("H", 0.0) * h_score
                + weights.get("C", 0.0) * c_score
                + weights.get("S", 0.0) * s_score
            )
        else:
            f0, h_score, c_score, s_score = best
            method_used = "harmonic_candidates"
            fallback_reason = None

        components = {
            "H": float(h_score),
            "C": float(c_score),
            "S": float(s_score),
            "HPS_f0": float(hps_f0),
            "AC_f0": float(ac_f0),
            "analysis_diagnostics": {
                "primary_method_used": method_used,
                "attempted_methods": attempted_methods,
                "strategy_path": strategy_path,
                "fallback_reason": fallback_reason,
            },
        }
        frames.append(PitchFrame(time_index=t, f0_hz=float(f0), salience=float(best_score), components=components))
        prev_f0 = float(f0)

    return frames
