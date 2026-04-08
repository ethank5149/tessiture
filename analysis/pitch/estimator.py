"""Pitch estimation helpers (HPS, autocorrelation, salience, PYIN).

Example:
    frames = estimate_pitch_frames(spectrum, frequencies, harmonic_frames)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from analysis.dsp.peak_detection import HarmonicFrame

logger = logging.getLogger(__name__)

_DEFAULT_VOICED_SALIENCE_THRESHOLD: float = float(os.getenv("TESSITURE_VOICED_MIN_SALIENCE", "0.3"))
_DEFAULT_VOICED_MIN_F0_HZ: float = float(os.getenv("TESSITURE_VOICED_MIN_HZ", "80.0"))
_DEFAULT_VOICED_MAX_F0_HZ: float = float(os.getenv("TESSITURE_VOICED_MAX_HZ", "1200.0"))
_USE_PYIN_PRIMARY: bool = os.getenv("TESSITURE_PITCH_METHOD", "pyin").lower() != "legacy"


def _pyin_estimate(
    audio: np.ndarray,
    sample_rate: int,
    hop_length: int,
    fmin: float = _DEFAULT_VOICED_MIN_F0_HZ,
    fmax: float = _DEFAULT_VOICED_MAX_F0_HZ,
    frame_length: Optional[int] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Run librosa PYIN pitch estimation.

    Returns (f0, voiced_flag, voiced_probabilities) or None if librosa
    is unavailable.  PYIN provides probabilistic voicing decisions and
    sub-cent pitch resolution — significantly more accurate than HPS or
    naive autocorrelation.

    CRITICAL: ``frame_length`` MUST match the STFT ``n_fft`` used by
    the rest of the pipeline.  When they differ, PYIN and the STFT
    produce different numbers of frames and every pitch value ends up
    associated with the wrong time position.
    """
    try:
        import librosa
    except ImportError:
        return None

    # Default to 2048 only as a safety net — callers should always pass
    # frame_length explicitly to match their STFT n_fft.
    if frame_length is None:
        frame_length = 2048
        logger.warning(
            "pyin_estimate called without explicit frame_length; "
            "defaulting to %d — this may cause frame misalignment with the STFT",
            frame_length,
        )

    try:
        f0, voiced_flag, voiced_probs = librosa.pyin(
            audio,
            sr=sample_rate,
            frame_length=frame_length,
            hop_length=hop_length,
            fmin=float(fmin),
            fmax=float(fmax),
            fill_na=0.0,
        )
        return np.asarray(f0), np.asarray(voiced_flag), np.asarray(voiced_probs)
    except Exception:
        logger.debug("pyin_estimate_failed", exc_info=True)
        return None


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
    """Estimate pitch using autocorrelation for a single frame.

    Uses parabolic interpolation around the correlation peak for sub-sample
    accuracy, reducing quantization error from ~17 cents to ~1–2 cents.
    """
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
    peak_idx = int(np.argmax(search))
    lag = peak_idx + min_lag
    if lag <= 0:
        return 0.0
    # Parabolic interpolation: fit a parabola through the peak and its
    # two neighbours to find the sub-sample peak location.
    if 0 < peak_idx < len(search) - 1:
        alpha = float(search[peak_idx - 1])
        beta = float(search[peak_idx])
        gamma = float(search[peak_idx + 1])
        denom = alpha - 2.0 * beta + gamma
        if abs(denom) > 1e-12:
            delta = 0.5 * (alpha - gamma) / denom
            lag = float(lag) + delta
    if lag <= 0.0:
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
    # Pitch distance in octaves (log2 ratio)
    log2_ratio = abs(np.log2(max(prev_f0, f0) / min(prev_f0, f0)))
    # Penalize ALL pitch jumps proportionally — including octave jumps.
    # The old code gave zero penalty for exact octave errors, which let the
    # path optimizer freely select octave-wrong candidates.
    # Smooth exponential: score ≈ 1.0 for same pitch, ≈ 0.37 at ±1 semitone,
    # ≈ 0.05 at ±1 octave, ≈ 0.0 beyond.
    return float(np.exp(-log2_ratio * 3.0))


def compute_voicing_mask(
    pitch_frames: List[PitchFrame],
    salience_threshold: float = _DEFAULT_VOICED_SALIENCE_THRESHOLD,
    min_f0_hz: float = _DEFAULT_VOICED_MIN_F0_HZ,
    max_f0_hz: float = _DEFAULT_VOICED_MAX_F0_HZ,
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


def _median_filter_pitch(f0_array: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Apply median filter to pitch track to suppress isolated octave errors.

    Only filters voiced frames (f0 > 0); unvoiced frames stay at 0.
    Works in log-frequency space so that the filter is perceptually uniform.
    """
    out = f0_array.copy()
    voiced_mask = out > 0.0
    if np.sum(voiced_mask) < kernel_size:
        return out
    log_f0 = np.where(voiced_mask, np.log2(np.maximum(out, 1.0)), 0.0)
    half = kernel_size // 2
    for i in range(len(log_f0)):
        if not voiced_mask[i]:
            continue
        lo = max(0, i - half)
        hi = min(len(log_f0), i + half + 1)
        neighborhood = log_f0[lo:hi]
        voiced_neighbors = neighborhood[neighborhood > 0.0]
        if len(voiced_neighbors) >= 3:
            med = float(np.median(voiced_neighbors))
            # Only correct if deviation > ~0.4 octaves (≈ a tritone) — likely an error
            if abs(log_f0[i] - med) > 0.4:
                out[i] = float(2.0 ** med)
    return out


def estimate_pitch_frames(
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    harmonic_frames: List[HarmonicFrame],
    audio: Optional[np.ndarray] = None,
    sample_rate: int = 44100,
    hop_length: int = 512,
    n_fft: int = 4096,
    weights: Optional[Dict[str, float]] = None,
) -> List[PitchFrame]:
    """Estimate pitch per frame using PYIN (primary) with HPS/AC fallback.

    When audio is available and PYIN is enabled (default), librosa PYIN
    provides the primary f0 estimate with sub-cent resolution and
    probabilistic voicing.  The legacy HPS + harmonic candidates pipeline
    runs in parallel as a cross-check and fills in diagnostics.

    When PYIN is unavailable (no librosa, no audio, or env
    TESSITURE_PITCH_METHOD=legacy), the function falls back to the
    original HPS/autocorrelation/salience pipeline.

    Args:
        spectrum: Magnitude spectrogram (freq x time).
        frequencies: Frequency grid.
        harmonic_frames: Harmonic candidates per frame.
        audio: Optional mono audio array for PYIN and autocorrelation.
        sample_rate: Sampling rate in Hz.
        hop_length: Hop length in samples for framing.
        n_fft: FFT size — MUST match the STFT n_fft so PYIN frame counts align.
        weights: Optional weights for salience terms (keys "H", "C", "S").

    Returns:
        List of PitchFrame objects.
    """
    if weights is None:
        weights = {"H": 0.474, "C": 0.263, "S": 0.263}

    n_frames = spectrum.shape[1]

    # --- PYIN primary pass (when available) --------------------------------
    pyin_f0: Optional[np.ndarray] = None
    pyin_voiced: Optional[np.ndarray] = None
    pyin_probs: Optional[np.ndarray] = None

    if _USE_PYIN_PRIMARY and audio is not None:
        pyin_result = _pyin_estimate(audio, sample_rate, hop_length, frame_length=n_fft)
        if pyin_result is not None:
            pyin_f0, pyin_voiced, pyin_probs = pyin_result
            logger.info(
                "pyin_primary_pass n_frames=%d pyin_frames=%d voiced=%d",
                n_frames,
                len(pyin_f0),
                int(np.sum(pyin_voiced)) if pyin_voiced is not None else 0,
            )

    # --- Legacy HPS pass ---------------------------------------------------
    hps_spec, hps_freqs = harmonic_product_spectrum(spectrum, frequencies)
    frames: List[PitchFrame] = []
    prev_f0 = 0.0

    for t in range(n_frames):
        # --- PYIN result for this frame ------------------------------------
        has_pyin = (pyin_f0 is not None and t < len(pyin_f0)
                    and pyin_voiced is not None and t < len(pyin_voiced))
        pyin_frame_f0 = float(pyin_f0[t]) if has_pyin else 0.0
        pyin_frame_voiced = bool(pyin_voiced[t]) if has_pyin else False
        pyin_frame_prob = float(pyin_probs[t]) if (has_pyin and pyin_probs is not None and t < len(pyin_probs)) else 0.0

        # --- Legacy harmonic/HPS/AC path ----------------------------------
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

        # Score legacy candidates
        legacy_best = None
        legacy_best_score = -np.inf
        for cand in candidates:
            f0 = cand.f0
            h_score = cand.score
            c_score = _continuity_score(prev_f0, f0)
            s_score = spectral_prominence(spectrum[:, t], frequencies, f0)
            score = (weights.get("H", 0.0) * h_score
                     + weights.get("C", 0.0) * c_score
                     + weights.get("S", 0.0) * s_score)
            if score > legacy_best_score:
                legacy_best_score = score
                legacy_best = (f0, h_score, c_score, s_score)

        # Resolve legacy fallback f0
        if legacy_best is not None:
            legacy_f0, h_score, c_score, s_score = legacy_best
            legacy_method = "harmonic_candidates"
            fallback_reason: Optional[str] = None
        else:
            if hps_f0 > 0.0 and hps_frame.size > 0:
                hps_peak = float(np.max(hps_frame))
                hps_median = float(np.median(hps_frame))
                hps_voiced = hps_median > 0.0 and (hps_peak / hps_median) >= 5.0
            else:
                hps_voiced = False

            if hps_voiced and hps_f0 > 0.0:
                legacy_f0 = hps_f0
                legacy_method = "hps_fallback"
                fallback_reason = "no_harmonic_candidates"
            elif ac_f0 > 0.0:
                legacy_f0 = ac_f0
                legacy_method = "autocorrelation_fallback"
                fallback_reason = "no_harmonic_candidates_and_hps_not_voiced"
            else:
                legacy_f0 = 0.0
                legacy_method = "no_pitch_detected"
                fallback_reason = "no_harmonic_candidates_and_no_viable_fallback"

            h_score = float(np.max(hps_frame)) if hps_frame.size else 0.0
            c_score = _continuity_score(prev_f0, legacy_f0)
            s_score = spectral_prominence(spectrum[:, t], frequencies, legacy_f0)
            legacy_best_score = (weights.get("H", 0.0) * h_score
                                 + weights.get("C", 0.0) * c_score
                                 + weights.get("S", 0.0) * s_score)

        # --- Select primary f0: PYIN > legacy ------------------------------
        if has_pyin and pyin_frame_voiced and pyin_frame_f0 > 0.0:
            f0 = pyin_frame_f0
            salience = float(max(pyin_frame_prob, legacy_best_score))
            method_used = "pyin"
        else:
            f0 = legacy_f0
            salience = float(legacy_best_score)
            method_used = legacy_method

        attempted_methods = (["pyin"] if has_pyin else []) + [
            "harmonic_candidates", "hps_peak_ratio_gate", "autocorrelation",
        ]
        strategy_path = ("pyin -> " if has_pyin else "") + "harmonic_candidates -> hps_peak_ratio_gate -> autocorrelation"

        components = {
            "H": float(h_score),
            "C": float(c_score),
            "S": float(s_score),
            "HPS_f0": float(hps_f0),
            "AC_f0": float(ac_f0),
            "PYIN_f0": float(pyin_frame_f0) if has_pyin else None,
            "PYIN_prob": float(pyin_frame_prob) if has_pyin else None,
            "analysis_diagnostics": {
                "primary_method_used": method_used,
                "attempted_methods": attempted_methods,
                "strategy_path": strategy_path,
                "fallback_reason": fallback_reason,
            },
        }
        frames.append(PitchFrame(time_index=t, f0_hz=float(f0),
                                 salience=float(salience), components=components))
        prev_f0 = float(f0)

    # --- Post-processing: median filter to suppress octave errors -----------
    if len(frames) >= 5:
        raw_f0 = np.array([f.f0_hz for f in frames], dtype=np.float32)
        filtered_f0 = _median_filter_pitch(raw_f0, kernel_size=5)
        for i, f in enumerate(frames):
            if abs(filtered_f0[i] - raw_f0[i]) > 1e-3:
                frames[i] = PitchFrame(
                    time_index=f.time_index,
                    f0_hz=float(filtered_f0[i]),
                    salience=f.salience,
                    components={**f.components, "_pre_median_f0": float(raw_f0[i])},
                )

    return frames
