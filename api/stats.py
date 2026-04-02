"""Statistical and inferential functions for the Tessiture API.

This module contains functions for bootstrap analysis, confidence intervals,
and statistical inference used in the analysis pipeline.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import numpy as np

from api import config
from api.utils import _as_finite_array, _safe_float

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _build_reference_calibration_uncertainty() -> Dict[str, Any]:
    """Build reference calibration uncertainty using LHS sampling.
    
    Returns:
        Dictionary containing calibration uncertainty metrics.
    """
    from calibration.monte_carlo.uncertainty_analyzer import summarize_uncertainty
    from calibration.reference_generation.lhs_sampler import lhs_sample
    from calibration.reference_generation.parameter_ranges import get_default_parameter_ranges

    try:
        parameter_ranges = dict(get_default_parameter_ranges())
        parameter_ranges["note_count"] = (1.0, 1.0)
        parameter_ranges["duration_s"] = (0.1, 0.1)

        sampled_params = lhs_sample(
            max(1, config.REFERENCE_CALIBRATION_SAMPLE_COUNT),
            parameter_ranges,
            seed=config.REFERENCE_CALIBRATION_SEED,
        )

        reference_results: List[Dict[str, Any]] = []
        for params in sampled_params:
            f0_hz = _safe_float(params.get("f0_hz"))
            detune_cents = _safe_float(params.get("detune_cents")) or 0.0
            if f0_hz is None or f0_hz <= 0.0:
                continue

            note_frequency_hz = float(f0_hz * (2.0 ** (detune_cents / 1200.0)))
            modeled_pitch_error_cents = float(0.9 * detune_cents)
            reference_results.append(
                {
                    "metadata": {"note_frequencies_hz": [note_frequency_hz]},
                    "pitch_error_cents": [modeled_pitch_error_cents],
                }
            )

        uncertainty = summarize_uncertainty(reference_results)
    except Exception:
        logger.warning("reference_calibration_uncertainty_build_failed", exc_info=True)
        uncertainty = summarize_uncertainty([])
        reference_results = []

    uncertainty["reference_source"] = "generated_ground_truth_reference"
    uncertainty["reference_seed"] = config.REFERENCE_CALIBRATION_SEED
    uncertainty["reference_dataset_size"] = len(reference_results)
    uncertainty["reference_voiced_frame_count"] = len(reference_results)
    return uncertainty


def _resolve_inferential_preset(metadata: Optional[Mapping[str, Any]]) -> tuple[str, Dict[str, float]]:
    """Resolve the inferential preset from metadata.
    
    Args:
        metadata: Optional metadata dictionary.
        
    Returns:
        Tuple of preset name and null hypothesis values.
    """
    requested = None
    if isinstance(metadata, Mapping):
        requested = metadata.get("inferential_preset")
    preset = str(requested or config.DEFAULT_INFERENTIAL_PRESET).strip().lower()
    if preset not in config.INFERENTIAL_NULL_PRESETS:
        logger.warning(
            "inferential_preset_unknown preset=%s fallback=%s",
            preset,
            config.DEFAULT_INFERENTIAL_PRESET,
        )
        preset = (
            config.DEFAULT_INFERENTIAL_PRESET
            if config.DEFAULT_INFERENTIAL_PRESET in config.INFERENTIAL_NULL_PRESETS
            else "casual"
        )
    return preset, dict(config.INFERENTIAL_NULL_PRESETS[preset])


def _bootstrap_two_sided_p_value(
    replicates: np.ndarray,
    null_value: Optional[float],
) -> Optional[float]:
    """Calculate a two-sided bootstrap p-value.
    
    Args:
        replicates: Bootstrap replicates.
        null_value: Null hypothesis value.
        
    Returns:
        Two-sided p-value, or None if not computable.
    """
    if null_value is None or replicates.size == 0:
        return None
    left_tail = float(np.mean(replicates <= float(null_value)))
    right_tail = float(np.mean(replicates >= float(null_value)))
    return float(np.clip(2.0 * min(left_tail, right_tail), 0.0, 1.0))


def _build_metric_inference(
    metric_name: str,
    values: np.ndarray,
    reducer: Callable[[np.ndarray], float],
    null_value: Optional[float],
    unit: str,
    confidence_level: float,
    bootstrap_samples: int,
    rng: np.random.Generator,
) -> Dict[str, Any]:
    """Build inference results for a single metric.
    
    Args:
        metric_name: Name of the metric.
        values: Observed values.
        reducer: Function to compute the point estimate.
        null_value: Null hypothesis value.
        unit: Unit of the metric.
        confidence_level: Confidence level for CI.
        bootstrap_samples: Number of bootstrap samples.
        rng: Random number generator.
        
    Returns:
        Dictionary containing estimate, CI, and p-value.
    """
    logger.debug(
        "analysis_metric_inference_build_start metric=%s n_values=%d confidence_level=%.3f bootstrap_samples=%d unit=%s null_value=%s",
        metric_name,
        int(values.size),
        float(confidence_level),
        int(bootstrap_samples),
        unit,
        null_value,
    )

    if values.size == 0:
        payload: Dict[str, Any] = {
            "estimate": None,
            "confidence_interval": {
                "level": confidence_level,
                "low": None,
                "high": None,
            },
            "p_value": None,
            "null_hypothesis": {
                "value": null_value,
                "description": f"{metric_name} equals {null_value}",
            },
            "n_samples": 0,
            "unit": unit,
        }
        logger.debug("analysis_metric_inference_build_empty metric=%s", metric_name)
        return payload

    samples = np.asarray(values, dtype=float)
    sample_size = int(samples.size)
    estimate = float(reducer(samples))

    replicates = np.empty(int(bootstrap_samples), dtype=float)
    for idx in range(int(bootstrap_samples)):
        sampled = rng.choice(samples, size=sample_size, replace=True)
        replicates[idx] = float(reducer(sampled))

    # --- BCa (Bias-Corrected and Accelerated) confidence interval ----------
    # Falls back to percentile bootstrap if BCa computation fails.
    from scipy import stats as _scipy_stats

    tail = (1.0 - float(confidence_level)) / 2.0
    alpha_lo = tail
    alpha_hi = 1.0 - tail

    try:
        # Bias correction factor z0: proportion of replicates below the
        # point estimate, mapped through the inverse normal CDF.
        prop_below = float(np.mean(replicates < estimate))
        prop_below = np.clip(prop_below, 1e-10, 1.0 - 1e-10)
        z0 = float(_scipy_stats.norm.ppf(prop_below))

        # Acceleration factor a: estimated from jackknife influence values.
        jackknife_values = np.empty(sample_size, dtype=float)
        for i in range(sample_size):
            jack_sample = np.concatenate([samples[:i], samples[i + 1:]])
            jackknife_values[i] = float(reducer(jack_sample))
        jack_mean = float(np.mean(jackknife_values))
        jack_diff = jack_mean - jackknife_values
        sum_cubed = float(np.sum(jack_diff ** 3))
        sum_squared = float(np.sum(jack_diff ** 2))
        if sum_squared > 0.0:
            a = sum_cubed / (6.0 * (sum_squared ** 1.5))
        else:
            a = 0.0

        # Adjusted quantiles
        z_lo = float(_scipy_stats.norm.ppf(alpha_lo))
        z_hi = float(_scipy_stats.norm.ppf(alpha_hi))

        def _bca_quantile(z_alpha: float) -> float:
            numerator = z0 + z_alpha
            adjusted = z0 + numerator / (1.0 - a * numerator)
            return float(np.clip(_scipy_stats.norm.cdf(adjusted), 1e-10, 1.0 - 1e-10))

        ci_low = float(np.quantile(replicates, _bca_quantile(z_lo)))
        ci_high = float(np.quantile(replicates, _bca_quantile(z_hi)))
    except Exception:
        # Fallback to plain percentile bootstrap
        logger.debug("bca_bootstrap_fallback metric=%s", metric_name)
        ci_low = float(np.quantile(replicates, alpha_lo))
        ci_high = float(np.quantile(replicates, alpha_hi))

    payload = {
        "estimate": estimate,
        "confidence_interval": {
            "level": confidence_level,
            "low": ci_low,
            "high": ci_high,
        },
        "p_value": _bootstrap_two_sided_p_value(replicates, null_value),
        "null_hypothesis": {
            "value": null_value,
            "description": f"{metric_name} equals {null_value}",
        },
        "n_samples": sample_size,
        "unit": unit,
    }

    logger.debug(
        "analysis_metric_inference_build_done metric=%s estimate=%s ci_low=%s ci_high=%s p_value=%s n_sample=%s",
        metric_name,
        payload.get("estimate") if isinstance(payload, Mapping) else None,
        payload.get("confidence_interval", {}).get("low") if isinstance(payload, Mapping) else None,
        payload.get("confidence_interval", {}).get("high") if isinstance(payload, Mapping) else None,
        payload.get("p_value") if isinstance(payload, Mapping) else None,
        sample_size,
    )
    return payload


def _build_inferential_statistics(
    voiced_f0: Sequence[float],
    voiced_midi: Sequence[float],
    pitch_errors: Sequence[float],
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build comprehensive inferential statistics for pitch analysis.
    
    Args:
        voiced_f0: Voiced f0 values in Hz.
        voiced_midi: Voiced MIDI values.
        pitch_errors: Pitch error values in cents.
        metadata: Optional metadata including inferential preset.
        
    Returns:
        Dictionary containing all metric inferences.
    """
    from api.pitch_utils import (
        _pitch_value_to_note_name,
        _unit_supports_pitch_note_names,
    )

    preset_name, nulls = _resolve_inferential_preset(metadata)
    confidence_level = float(np.clip(config.BOOTSTRAP_CONFIDENCE_LEVEL, 0.5, 0.999))
    bootstrap_samples = max(200, int(config.BOOTSTRAP_SAMPLES))
    rng = np.random.default_rng(20260302)

    voiced_f0_arr = _as_finite_array(voiced_f0)
    voiced_midi_arr = _as_finite_array(voiced_midi)
    pitch_error_arr = _as_finite_array(pitch_errors)

    metrics = {
        "f0_mean_hz": _build_metric_inference(
            "f0_mean_hz",
            voiced_f0_arr,
            lambda data: float(np.mean(data)),
            nulls.get("f0_mean_hz"),
            "Hz",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
        "f0_min_hz": _build_metric_inference(
            "f0_min_hz",
            voiced_f0_arr,
            lambda data: float(np.min(data)),
            nulls.get("f0_min_hz"),
            "Hz",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
        "f0_max_hz": _build_metric_inference(
            "f0_max_hz",
            voiced_f0_arr,
            lambda data: float(np.max(data)),
            nulls.get("f0_max_hz"),
            "Hz",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
        "tessitura_center_midi": _build_metric_inference(
            "tessitura_center_midi",
            voiced_midi_arr,
            lambda data: float(np.mean(data)),
            nulls.get("tessitura_center_midi"),
            "MIDI",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
        "pitch_error_mean_cents": _build_metric_inference(
            "pitch_error_mean_cents",
            pitch_error_arr,
            lambda data: float(np.mean(data)),
            nulls.get("pitch_error_mean_cents"),
            "cents",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
    }

    # Add note-name annotations for pitch-unit metrics (Hz, MIDI)
    for payload in metrics.values():
        if not isinstance(payload, Mapping):
            continue
        unit = payload.get("unit")
        if not _unit_supports_pitch_note_names(unit):
            continue

        estimate_note = _pitch_value_to_note_name(payload.get("estimate"), unit)
        if estimate_note is not None:
            payload["estimate_note"] = estimate_note

        confidence_interval = payload.get("confidence_interval")
        if isinstance(confidence_interval, Mapping):
            low_note = _pitch_value_to_note_name(confidence_interval.get("low"), unit)
            high_note = _pitch_value_to_note_name(confidence_interval.get("high"), unit)
            if low_note is not None:
                confidence_interval["low_note"] = low_note
            if high_note is not None:
                confidence_interval["high_note"] = high_note

        null_hypothesis = payload.get("null_hypothesis")
        if isinstance(null_hypothesis, Mapping):
            value_note = _pitch_value_to_note_name(null_hypothesis.get("value"), unit)
            if value_note is not None:
                null_hypothesis["value_note"] = value_note

    for metric_name, payload in metrics.items():
        ci = payload.get("confidence_interval") if isinstance(payload, Mapping) else None
        logger.info(
            "analysis_metric_inference metric=%s preset=%s estimate=%s ci_low=%s ci_high=%s p_value=%s n_sample=%s",
            metric_name,
            preset_name,
            payload.get("estimate") if isinstance(payload, Mapping) else None,
            ci.get("low") if isinstance(ci, Mapping) else None,
            ci.get("high") if isinstance(ci, Mapping) else None,
            payload.get("p_value") if isinstance(payload, Mapping) else None,
            payload.get("n_samples") if isinstance(payload, Mapping) else None,
        )

    return {
        "preset": preset_name,
        "confidence_level": confidence_level,
        "bootstrap_samples": bootstrap_samples,
        "metrics": metrics,
    }


def _build_calibration_summary(uncertainty: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a summary of calibration uncertainty metrics.
    
    Args:
        uncertainty: Uncertainty metrics from calibration.
        
    Returns:
        Summary dictionary with key metrics.
    """
    uncertainty_payload = uncertainty if isinstance(uncertainty, Mapping) else {}

    frequency_bins = _as_finite_array(uncertainty_payload.get("frequency_bins_hz") or [])
    sample_counts = _as_finite_array(uncertainty_payload.get("sample_counts") or [])
    pitch_bias = _as_finite_array(uncertainty_payload.get("pitch_bias_cents") or [])
    pitch_variance = _as_finite_array(uncertainty_payload.get("pitch_variance_cents2") or [])

    def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> Optional[float]:
        size = min(values.size, weights.size)
        if size <= 0:
            return None
        safe_weights = np.clip(weights[:size], 0.0, None)
        total = float(np.sum(safe_weights))
        if total <= 0.0:
            return None
        return float(np.sum(values[:size] * safe_weights) / total)

    paired_bias_size = min(pitch_bias.size, sample_counts.size)
    paired_variance_size = min(pitch_variance.size, sample_counts.size)
    paired_moment_size = min(pitch_bias.size, pitch_variance.size, sample_counts.size)

    bias_values = pitch_bias[:paired_bias_size]
    bias_counts = sample_counts[:paired_bias_size]
    variance_values = pitch_variance[:paired_variance_size]
    variance_counts = sample_counts[:paired_variance_size]
    moment_bias_values = pitch_bias[:paired_moment_size]
    moment_variance_values = pitch_variance[:paired_moment_size]
    moment_counts = sample_counts[:paired_moment_size]

    populated_bins = sample_counts[sample_counts > 0.0]
    populated_bias_mask = bias_counts > 0.0

    mean_pitch_bias = _weighted_mean(bias_values, bias_counts)
    mean_pitch_variance = _weighted_mean(variance_values, variance_counts)
    max_abs_pitch_bias = (
        float(np.max(np.abs(bias_values[populated_bias_mask])))
        if bias_values.size and np.any(populated_bias_mask)
        else None
    )

    pitch_error_std: Optional[float] = None
    populated_moment_mask = moment_counts > 0.0
    if moment_bias_values.size and np.any(populated_moment_mask):
        weights = np.clip(moment_counts[populated_moment_mask], 0.0, None)
        total = float(np.sum(weights))
        if total > 0.0 and mean_pitch_bias is not None:
            centered = moment_bias_values[populated_moment_mask] - float(mean_pitch_bias)
            second_moment = np.sum(
                weights * (moment_variance_values[populated_moment_mask] + np.square(centered))
            ) / total
            pitch_error_std = float(np.sqrt(max(float(second_moment), 0.0)))

    reference_sample_count = (
        int(round(float(np.sum(np.clip(sample_counts, 0.0, None))))) if sample_counts.size else 0
    )

    mean_frame_uncertainty = _safe_float(uncertainty_payload.get("reference_mean_frame_uncertainty_midi"))

    voiced_frame_count_value = _safe_float(uncertainty_payload.get("reference_voiced_frame_count"))
    voiced_frame_count = (
        int(round(voiced_frame_count_value))
        if voiced_frame_count_value is not None
        else reference_sample_count
    )

    return {
        "source": str(uncertainty_payload.get("reference_source") or "generated_ground_truth_reference"),
        "reference_sample_count": reference_sample_count,
        "reference_frequency_min_hz": float(np.min(frequency_bins)) if frequency_bins.size else None,
        "reference_frequency_max_hz": float(np.max(frequency_bins)) if frequency_bins.size else None,
        "frequency_bin_count": int(max(frequency_bins.size - 1, 0)),
        "populated_frequency_bin_count": int(populated_bins.size),
        "mean_pitch_bias_cents": mean_pitch_bias,
        "max_abs_pitch_bias_cents": max_abs_pitch_bias,
        "mean_pitch_variance_cents2": mean_pitch_variance,
        "pitch_error_mean_cents": mean_pitch_bias,
        "pitch_error_std_cents": pitch_error_std,
        "mean_frame_uncertainty_midi": mean_frame_uncertainty,
        "voiced_frame_count": voiced_frame_count,
    }
