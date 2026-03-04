"""Monte Carlo perturbation utilities for calibration."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence

import numpy as np


def _sample_from_config(value: Any, rng: np.random.Generator) -> Any:
    """Sample a value from a configuration spec."""

    if isinstance(value, Mapping):
        if "choices" in value:
            choices = list(value["choices"])
            if not choices:
                return None
            index = int(rng.integers(0, len(choices)))
            return choices[index]
        low = value.get("low", value.get("min"))
        high = value.get("high", value.get("max"))
        if low is not None and high is not None:
            return float(rng.uniform(float(low), float(high)))
        mean = value.get("mean")
        std = value.get("std")
        if mean is not None and std is not None:
            return float(rng.normal(float(mean), float(std)))
        if "value" in value:
            return value["value"]
        return value

    if isinstance(value, (list, tuple, np.ndarray)):
        if len(value) == 2 and np.all(np.isfinite(value)):
            return float(rng.uniform(float(value[0]), float(value[1])))
        if len(value) > 0:
            index = int(rng.integers(0, len(value)))
            return value[index]
        return None

    return value


def _build_perturbation_params(
    perturb_config: Mapping[str, Any] | None,
    rng: np.random.Generator,
) -> Dict[str, Any]:
    """Build a parameter dictionary by sampling perturbation config."""

    if not perturb_config:
        return {}

    params: Dict[str, Any] = {}
    for key, value in perturb_config.items():
        if key == "resample_ppm" and isinstance(value, (int, float)):
            span = float(value)
            params[key] = float(rng.uniform(-span, span))
        else:
            params[key] = _sample_from_config(value, rng)
    return params


def apply_perturbations(
    audio: np.ndarray,
    sample_rate: int,
    params: Mapping[str, Any],
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply Monte Carlo perturbations to an audio signal.

    Args:
        audio: Input audio samples.
        sample_rate: Sample rate in Hz.
        params: Perturbation parameters.
        rng: Random generator for deterministic perturbations.

    Returns:
        Perturbed audio signal.
    """

    _ = sample_rate
    perturbed = np.asarray(audio, dtype=float).copy()

    drift_db = float(params.get("amplitude_drift_db", 0.0) or 0.0)
    if drift_db != 0.0 and perturbed.size > 0:
        end_db = float(rng.uniform(-abs(drift_db), abs(drift_db)))
        drift_curve = np.linspace(0.0, end_db, num=perturbed.size, dtype=float)
        drift = 10.0 ** (drift_curve / 20.0)
        perturbed *= drift

    phase_jitter_std = float(params.get("phase_jitter_std", 0.0) or 0.0)
    if phase_jitter_std > 0.0 and perturbed.size > 1:
        spectrum = np.fft.rfft(perturbed)
        n_bins = spectrum.shape[0] if spectrum.ndim == 1 else spectrum.shape[0]
        # Generate smoothly-varying phase perturbation using bandlimited noise
        # Correlation length: ~10% of spectrum length (smooth variation across frequency)
        correlation_bins = max(1, n_bins // 10)
        # Low-pass filter white noise to get smooth phase variation
        raw_phase = rng.normal(scale=float(phase_jitter_std), size=(n_bins,))
        # Apply simple box-car smoothing for correlation
        kernel = np.ones(correlation_bins, dtype=float) / correlation_bins
        smooth_phase = np.convolve(raw_phase, kernel, mode='same')
        # Scale to maintain approximately the target std after smoothing
        smooth_std = float(np.std(smooth_phase)) if np.std(smooth_phase) > 0 else 1.0
        smooth_phase = smooth_phase * (float(phase_jitter_std) / smooth_std)
        spectrum = spectrum * np.exp(1j * smooth_phase)
        perturbed = np.fft.irfft(spectrum, n=perturbed.size)

    shift = int(round(float(params.get("window_shift_samples", 0.0) or 0.0)))
    if shift != 0 and perturbed.size > 0:
        if shift > 0:
            pad = np.zeros(shift, dtype=float)
            perturbed = np.concatenate([pad, perturbed[:-shift]])
        else:
            shift = abs(shift)
            pad = np.zeros(shift, dtype=float)
            perturbed = np.concatenate([perturbed[shift:], pad])

    resample_ratio = params.get("resample_ratio")
    resample_ppm = params.get("resample_ppm")
    ratio = None
    if resample_ratio is not None:
        ratio = float(resample_ratio)
    elif resample_ppm is not None:
        ratio = 1.0 + float(resample_ppm) * 1e-6

    if ratio is not None and ratio > 0 and ratio != 1.0 and perturbed.size > 1:
        n_samples = perturbed.size
        # Simulate sample-clock drift: the signal was recorded at a slightly
        # different rate, so its time axis is stretched by 1/ratio relative to
        # the expected playback rate.
        stretched_axis = np.linspace(0.0, 1.0 / ratio, n_samples, endpoint=False)
        # Clamp to valid range [0, 1)
        stretched_axis = np.clip(stretched_axis, 0.0, 1.0 - 1.0 / n_samples)
        original_axis = np.linspace(0.0, 1.0, n_samples, endpoint=False)
        perturbed = np.interp(stretched_axis, original_axis, perturbed)

    snr_db = params.get("snr_db")
    if snr_db is not None and np.isfinite(snr_db):
        signal_power = float(np.mean(perturbed ** 2)) if perturbed.size > 0 else 0.0
        if signal_power > 0.0:
            noise_power = signal_power / (10.0 ** (float(snr_db) / 10.0))
            noise = rng.normal(scale=np.sqrt(noise_power), size=perturbed.shape)
            perturbed = perturbed + noise

    return perturbed.astype(np.float32)


def run_monte_carlo(
    samples: Sequence[Any],
    n_realizations: int,
    perturb_config: Mapping[str, Any] | None,
    seed: int | None = None,
) -> List[Dict[str, Any]]:
    """Run Monte Carlo perturbations across reference samples.

    Args:
        samples: Iterable of sample tuples or dicts containing audio and metadata.
        n_realizations: Number of perturbed realizations per sample.
        perturb_config: Configuration of perturbation distributions.
        seed: Random seed for deterministic output.

    Returns:
        List of dictionaries containing perturbed audio and metadata.
    """

    rng = np.random.default_rng(seed)
    results: List[Dict[str, Any]] = []

    for sample_index, sample in enumerate(samples):
        if isinstance(sample, Mapping):
            audio = sample.get("audio")
            metadata = dict(sample.get("metadata", {}))
            sample_rate = int(sample.get("sample_rate", metadata.get("sample_rate", 44100)))
        elif isinstance(sample, (list, tuple)) and len(sample) == 2:
            audio, metadata = sample
            metadata = dict(metadata or {})
            sample_rate = int(metadata.get("sample_rate", 44100))
        else:
            raise ValueError("Each sample must be a dict or (audio, metadata) tuple.")

        if audio is None:
            raise ValueError("Sample audio is missing.")

        for realization_index in range(int(n_realizations)):
            params = _build_perturbation_params(perturb_config, rng)
            perturbed_audio = apply_perturbations(audio, sample_rate, params, rng)
            results.append(
                {
                    "reference_index": sample_index,
                    "realization_index": realization_index,
                    "audio": perturbed_audio,
                    "sample_rate": sample_rate,
                    "metadata": metadata,
                    "perturbations": params,
                }
            )

    return results


__all__ = ["apply_perturbations", "run_monte_carlo"]
