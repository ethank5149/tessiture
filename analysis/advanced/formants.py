"""Formant estimation utilities (F1/F2/F3 trajectories)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from analysis.dsp.peak_detection import _find_peaks
from analysis.dsp.preprocessing import preprocess_audio
from analysis.dsp.stft import compute_stft


@dataclass(frozen=True)
class FormantFrame:
    """Single-frame formant estimates with quality metrics."""

    time_s: float
    f1_hz: float
    f2_hz: float
    f3_hz: float
    bandwidths_hz: Tuple[float, float, float]
    confidences: Tuple[float, float, float]


@dataclass(frozen=True)
class FormantTrack:
    """Formant trajectories and quality metrics across frames."""

    times_s: np.ndarray
    f1_hz: np.ndarray
    f2_hz: np.ndarray
    f3_hz: np.ndarray
    bandwidths_hz: np.ndarray
    confidences: np.ndarray


def _smooth_spectrum(spectrum: np.ndarray, kernel_bins: int) -> np.ndarray:
    if kernel_bins <= 1:
        return spectrum
    kernel = np.ones(int(kernel_bins), dtype=np.float32)
    kernel /= float(np.sum(kernel))
    return np.apply_along_axis(lambda m: np.convolve(m, kernel, mode="same"), 0, spectrum)


def _peak_bandwidth(
    magnitude: np.ndarray,
    frequencies: np.ndarray,
    peak_frequency: float,
    peak_amplitude: float,
) -> float:
    if peak_frequency <= 0.0 or peak_amplitude <= 0.0:
        return 0.0
    idx = int(np.argmin(np.abs(frequencies - peak_frequency)))
    threshold = peak_amplitude / np.sqrt(2.0)
    left = idx
    while left > 0 and magnitude[left] >= threshold:
        left -= 1
    right = idx
    while right < magnitude.size - 1 and magnitude[right] >= threshold:
        right += 1
    if right <= left:
        return 0.0
    return float(frequencies[right] - frequencies[left])


def _band_confidence(magnitude: np.ndarray, band_mask: np.ndarray, peak_amplitude: float) -> float:
    if not np.any(band_mask):
        return 0.0
    band_mean = float(np.mean(magnitude[band_mask]))
    return float(peak_amplitude / (band_mean + 1e-12))


def _select_peak(
    peaks: Sequence,
    band: Tuple[float, float],
    min_frequency: float,
) -> Optional[Tuple[float, float]]:
    band_min, band_max = band
    candidates = [p for p in peaks if band_min <= p.frequency <= band_max and p.frequency > min_frequency]
    if not candidates:
        return None
    best = max(candidates, key=lambda p: p.amplitude)
    return float(best.frequency), float(best.amplitude)


def _pre_emphasize(audio: np.ndarray, alpha: float = 0.97) -> np.ndarray:
    """Apply first-order pre-emphasis filter: y[n] = x[n] - alpha * x[n-1].

    Pre-emphasis boosts high-frequency energy to flatten the spectral tilt
    caused by the glottal pulse spectrum (~-12 dB/octave), making higher
    formants more easily detectable.

    Args:
        audio: Input audio array.
        alpha: Pre-emphasis coefficient (typically 0.97).

    Returns:
        Pre-emphasized audio array.
    """
    if audio.size < 2:
        return audio.copy()
    result = np.empty_like(audio, dtype=np.float32)
    result[0] = audio[0]
    result[1:] = audio[1:] - float(alpha) * audio[:-1]
    return result


def _levinson_durbin(r: np.ndarray, order: int) -> np.ndarray:
    """Levinson-Durbin recursion for computing LPC coefficients.

    Solves the Yule-Walker equations R * a = -r[1:order+1] efficiently.

    Args:
        r: Autocorrelation sequence r[0], r[1], ..., r[order].
        order: LPC order.

    Returns:
        LPC coefficients a[1], a[2], ..., a[order] (not including the leading 1).
    """
    if r[0] <= 0.0:
        return np.zeros(order, dtype=np.float64)

    a = np.zeros(order, dtype=np.float64)
    e = float(r[0])

    for i in range(order):
        lam = -float(np.dot(a[:i], r[1:i+1][::-1]) + r[i + 1])
        lam /= e
        a_new = np.zeros(order, dtype=np.float64)
        a_new[:i] = a[:i] + lam * a[:i][::-1]
        a_new[i] = lam
        a = a_new
        e = e * (1.0 - lam ** 2)
        if e <= 0.0:
            break

    return a


def _compute_lpc_frame(
    frame: np.ndarray,
    order: int,
) -> np.ndarray:
    """Compute LPC coefficients for a single audio frame.

    Args:
        frame: Audio samples (windowed).
        order: LPC order (typically 10-14 for speech).

    Returns:
        LPC coefficient array a[1..order] (not including leading 1).
    """
    # Autocorrelation method
    n = frame.size
    r = np.array([
        float(np.dot(frame[:n - k], frame[k:])) / max(n, 1)
        for k in range(order + 1)
    ], dtype=np.float64)

    return _levinson_durbin(r, order)


def _lpc_poles_to_formants(
    lpc_coeffs: np.ndarray,
    sample_rate: int,
    min_freq_hz: float = 50.0,
    max_bandwidth_hz: float = 1000.0,
) -> List[Tuple[float, float]]:
    """Extract formant frequencies and bandwidths from LPC poles.

    Args:
        lpc_coeffs: LPC coefficients a[1..p] (not including leading 1).
        sample_rate: Audio sample rate in Hz.
        min_freq_hz: Minimum formant frequency to keep.
        max_bandwidth_hz: Maximum formant bandwidth to keep (Hz).

    Returns:
        Sorted list of (frequency_hz, bandwidth_hz) tuples for each formant.
    """
    if lpc_coeffs.size == 0:
        return []

    # Build the polynomial A(z) = 1 + a1*z^-1 + ... + ap*z^-p
    # np.roots expects polynomial coefficients in descending powers
    poly = np.concatenate([[1.0], lpc_coeffs.astype(float)])

    try:
        poles = np.roots(poly)
    except np.linalg.LinAlgError:
        return []

    formants: List[Tuple[float, float]] = []
    fs = float(sample_rate)

    for pole in poles:
        # Only keep poles in upper half-plane (positive imaginary part)
        if float(np.imag(pole)) <= 0.0:
            continue

        angle = float(np.angle(pole))
        if angle <= 0.0:
            continue

        freq_hz = angle * fs / (2.0 * float(np.pi))
        radius = float(np.abs(pole))

        # Bandwidth from pole radius: BW = -ln(|r|) * fs / pi
        if radius > 0.0 and radius < 1.0:
            bandwidth_hz = -float(np.log(radius)) * fs / float(np.pi)
        else:
            continue

        if freq_hz < min_freq_hz:
            continue
        if bandwidth_hz > max_bandwidth_hz:
            continue

        formants.append((freq_hz, bandwidth_hz))

    formants.sort(key=lambda x: x[0])
    return formants


def estimate_formants_lpc(
    audio: np.ndarray,
    sample_rate: int,
    *,
    lpc_order: int = 12,
    frame_length: int = 1024,
    hop_length: int = 512,
    pre_emphasis_alpha: float = 0.97,
    min_formant_freq: float = 100.0,
    max_formant_bw: float = 700.0,
    target_sr: int = 16000,
) -> "FormantTrack":
    """Estimate F1/F2/F3 formant trajectories using LPC analysis.

    This function implements the industry-standard LPC-based formant estimation
    approach, which models the vocal tract as an all-pole filter and extracts
    formant resonances as poles of the transfer function.

    Algorithm:
    1. Optional pre-emphasis to flatten glottal spectral tilt (~-12 dB/oct)
    2. Frame the signal with Hann window
    3. Compute LPC coefficients via autocorrelation + Levinson-Durbin
    4. Find roots of A(z) polynomial
    5. Convert pole angles/radii to formant frequencies/bandwidths

    Reference: Markel & Gray (1976), "Linear Prediction of Speech", Springer.

    Args:
        audio: Input audio samples.
        sample_rate: Input sample rate in Hz.
        lpc_order: LPC polynomial order (10-14 typical for speech).
        frame_length: Analysis frame length in samples (at target_sr).
        hop_length: Hop length in samples (at target_sr).
        pre_emphasis_alpha: Pre-emphasis coefficient (0 disables pre-emphasis).
        min_formant_freq: Minimum formant frequency to report (Hz).
        max_formant_bw: Maximum formant bandwidth to report (Hz).
        target_sr: Sample rate to use internally (16kHz is standard for speech LPC).

    Returns:
        FormantTrack with F1, F2, F3 trajectories extracted via LPC.
    """
    from analysis.dsp.preprocessing import preprocess_audio

    # Preprocess: resample to target SR (16kHz is standard for speech LPC)
    proc = preprocess_audio(
        audio, sample_rate,
        target_sr=target_sr,
        mono=True,
        normalize=True,
    )
    sig = proc.audio.astype(np.float64)
    sr = proc.sample_rate

    # Pre-emphasis
    if float(pre_emphasis_alpha) > 0.0:
        sig = _pre_emphasize(sig.astype(np.float32), alpha=float(pre_emphasis_alpha)).astype(np.float64)

    # Frame the signal
    n_samples = sig.size
    if n_samples < frame_length:
        sig = np.pad(sig, (0, frame_length - n_samples))
        n_samples = sig.size

    n_frames = 1 + (n_samples - frame_length) // hop_length
    window = np.hanning(frame_length)

    f1 = np.zeros(n_frames, dtype=np.float32)
    f2 = np.zeros(n_frames, dtype=np.float32)
    f3 = np.zeros(n_frames, dtype=np.float32)
    bandwidths = np.zeros((n_frames, 3), dtype=np.float32)
    confidences = np.zeros((n_frames, 3), dtype=np.float32)
    times = np.arange(n_frames, dtype=np.float32) * (float(hop_length) / float(sr))

    for t in range(n_frames):
        start = t * hop_length
        frame = sig[start : start + frame_length]
        if frame.size < frame_length:
            frame = np.pad(frame, (0, frame_length - frame.size))

        frame_windowed = frame * window

        lpc_a = _compute_lpc_frame(frame_windowed, order=lpc_order)
        formant_list = _lpc_poles_to_formants(
            lpc_a, sr,
            min_freq_hz=float(min_formant_freq),
            max_bandwidth_hz=float(max_formant_bw),
        )

        if len(formant_list) >= 1:
            f1[t] = float(formant_list[0][0])
            bw1 = float(formant_list[0][1])
            bandwidths[t, 0] = bw1
            # Confidence: narrow bandwidth = high confidence (normalized)
            confidences[t, 0] = float(np.clip(1.0 - bw1 / float(max_formant_bw), 0.0, 1.0))

        if len(formant_list) >= 2:
            f2[t] = float(formant_list[1][0])
            bw2 = float(formant_list[1][1])
            bandwidths[t, 1] = bw2
            confidences[t, 1] = float(np.clip(1.0 - bw2 / float(max_formant_bw), 0.0, 1.0))

        if len(formant_list) >= 3:
            f3[t] = float(formant_list[2][0])
            bw3 = float(formant_list[2][1])
            bandwidths[t, 2] = bw3
            confidences[t, 2] = float(np.clip(1.0 - bw3 / float(max_formant_bw), 0.0, 1.0))

    return FormantTrack(
        times_s=times,
        f1_hz=f1,
        f2_hz=f2,
        f3_hz=f3,
        bandwidths_hz=bandwidths,
        confidences=confidences,
    )


def estimate_formants_from_spectrum(
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    times: Optional[np.ndarray] = None,
    *,
    bands: Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]] = (
        (200.0, 1000.0),
        (700.0, 3000.0),
        (2000.0, 5000.0),
    ),
    min_db: float = -50.0,
    smoothing_bins: int = 5,
) -> FormantTrack:
    """Estimate F1/F2/F3 trajectories from a magnitude spectrogram.

    Args:
        spectrum: Magnitude spectrogram (freq x time).
        frequencies: Frequency grid (Hz) aligned with spectrum rows.
        times: Optional time vector in seconds (length = n_frames).
        bands: Frequency bands for (F1, F2, F3) search in Hz.
        min_db: Relative peak threshold for peak detection.
        smoothing_bins: Moving-average bins along frequency axis.
    """
    spectrum = np.asarray(spectrum, dtype=np.float32)
    frequencies = np.asarray(frequencies, dtype=np.float32)
    if spectrum.ndim != 2:
        raise ValueError("spectrum must be 2D (freq x time)")
    if frequencies.size != spectrum.shape[0]:
        raise ValueError("frequencies length must match spectrum rows")
    n_frames = spectrum.shape[1]
    if times is None:
        times = np.arange(n_frames, dtype=np.float32)
    else:
        times = np.asarray(times, dtype=np.float32)
    if times.shape[0] != n_frames:
        raise ValueError("times length must match spectrum columns")

    smoothed = _smooth_spectrum(spectrum, smoothing_bins)

    f1 = np.zeros(n_frames, dtype=np.float32)
    f2 = np.zeros(n_frames, dtype=np.float32)
    f3 = np.zeros(n_frames, dtype=np.float32)
    bandwidths = np.zeros((n_frames, 3), dtype=np.float32)
    confidences = np.zeros((n_frames, 3), dtype=np.float32)

    for t in range(n_frames):
        mag = smoothed[:, t]
        peaks = _find_peaks(mag, frequencies, min_db=min_db)
        prev_f = 0.0
        selections: List[Optional[Tuple[float, float]]] = []
        for band in bands:
            choice = _select_peak(peaks, band, prev_f)
            selections.append(choice)
            if choice is not None:
                prev_f = choice[0]

        for idx, (band, choice) in enumerate(zip(bands, selections)):
            if choice is None:
                continue
            freq, amp = choice
            band_mask = (frequencies >= band[0]) & (frequencies <= band[1])
            bandwidths[t, idx] = _peak_bandwidth(mag, frequencies, freq, amp)
            confidences[t, idx] = _band_confidence(mag, band_mask, amp)
            if idx == 0:
                f1[t] = freq
            elif idx == 1:
                f2[t] = freq
            else:
                f3[t] = freq

    return FormantTrack(
        times_s=times,
        f1_hz=f1,
        f2_hz=f2,
        f3_hz=f3,
        bandwidths_hz=bandwidths,
        confidences=confidences,
    )


def estimate_formants_from_audio(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 4096,
    hop_length: int = 512,
    target_sr: int = 44100,
    preprocess: bool = True,
    bands: Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]] = (
        (200.0, 1000.0),
        (700.0, 3000.0),
        (2000.0, 5000.0),
    ),
    min_db: float = -50.0,
    smoothing_bins: int = 5,
    method: str = "lpc",
) -> FormantTrack:
    """Estimate formants directly from audio.

    Args:
        method: "lpc" (default, recommended) uses LPC pole analysis — the
            standard approach in speech science.  "spectrum" uses the legacy
            smoothed-spectrum peak-picking method.  LPC is more robust for
            high-pitched voices where harmonics can masquerade as formants
            in the magnitude spectrum.
    """
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    if method == "lpc":
        try:
            return estimate_formants_lpc(
                audio,
                sample_rate,
                hop_length=hop_length,
            )
        except Exception as exc:
            _logger.debug("formant_lpc_failed, falling back to spectrum method: %s", exc)
            # Fall through to spectrum method

    # Spectrum peak-picking fallback
    if preprocess:
        result = preprocess_audio(audio, sample_rate, target_sr=target_sr)
        audio = result.audio
        sample_rate = int(result.sample_rate)
    stft = compute_stft(audio, sample_rate=sample_rate, n_fft=n_fft, hop_length=hop_length)
    return estimate_formants_from_spectrum(
        stft.spectrum,
        stft.frequencies,
        times=stft.times,
        bands=bands,
        min_db=min_db,
        smoothing_bins=smoothing_bins,
    )


def track_to_frames(track: FormantTrack) -> List[FormantFrame]:
    """Convert a FormantTrack to a list of FormantFrame objects."""
    frames: List[FormantFrame] = []
    for idx, time_s in enumerate(track.times_s):
        bandwidths = tuple(float(x) for x in track.bandwidths_hz[idx])
        confidences = tuple(float(x) for x in track.confidences[idx])
        frames.append(
            FormantFrame(
                time_s=float(time_s),
                f1_hz=float(track.f1_hz[idx]),
                f2_hz=float(track.f2_hz[idx]),
                f3_hz=float(track.f3_hz[idx]),
                bandwidths_hz=bandwidths,
                confidences=confidences,
            )
        )
    return frames


__all__ = [
    "FormantFrame",
    "FormantTrack",
    "estimate_formants_from_audio",
    "estimate_formants_from_spectrum",
    "estimate_formants_lpc",
    "track_to_frames",
]
