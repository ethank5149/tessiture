"""Tessitura analysis utilities for weighted pitch observations."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
import math
import numpy as np
from analysis.tessitura.vocal_range import _prepare_observations, compute_comfort_band, compute_range, compute_weighted_percentiles
@dataclass(frozen=True)
class WeightedPitchPDF:
    """Weighted pitch probability density function."""
    bin_edges: np.ndarray
    density: np.ndarray
    bin_centers: np.ndarray
    bin_size: float
    total_weight: float
@dataclass(frozen=True)
class StrainZone:
    """Represents a vocal strain zone derived from tessitura statistics."""
    label: str
    low: float
    high: float
    reason: str
@dataclass(frozen=True)
class TessituraMetrics:
    """Summary metrics for tessitura analysis."""
    count: int
    weight_sum: float
    range_min: float
    range_max: float
    tessitura_band: Tuple[float, float]
    comfort_band: Tuple[float, float]
    comfort_center: float
    variance: float
    std_dev: float
    mean_variance: float  # Variance of weighted mean: Σ(w²σ²)/(Σw)²; assumes fixed weights
    strain_zones: Tuple[StrainZone, ...]
@dataclass(frozen=True)
class TessituraAnalysis:
    """Full tessitura analysis including metrics and optional PDF."""
    metrics: TessituraMetrics
    pdf: Optional[WeightedPitchPDF]
def compute_weighted_pdf(
    pitches: Sequence[float],
    weights: Optional[Sequence[float]] = None,
    confidences: Optional[Sequence[float]] = None,
    *,
    bin_size: float = 0.1,
) -> WeightedPitchPDF:
    """Compute a weighted pitch PDF using a simple histogram.
    Args:
        pitches: Sequence of MIDI pitch values.
        weights: Optional per-observation weights.
        confidences: Optional per-observation confidences multiplied into weights.
        bin_size: Bin width in MIDI units.
    """
    values, weight_values, _ = _prepare_observations(pitches, weights=weights, confidences=confidences)
    if bin_size <= 0:
        raise ValueError("bin_size must be positive.")
    min_pitch = float(np.min(values))
    max_pitch = float(np.max(values))
    if math.isclose(min_pitch, max_pitch):
        half = bin_size * 0.5
        bin_edges = np.array([min_pitch - half, max_pitch + half], dtype=float)
    else:
        bin_edges = np.arange(min_pitch, max_pitch + bin_size, bin_size, dtype=float)
        if bin_edges.size < 2:
            bin_edges = np.array([min_pitch, max_pitch + bin_size], dtype=float)
    histogram, bin_edges = np.histogram(values, bins=bin_edges, weights=weight_values)
    total_weight = float(np.sum(weight_values))
    density = histogram / max(total_weight * bin_size, np.finfo(float).eps)
    bin_centers = bin_edges[:-1] + (bin_edges[1:] - bin_edges[:-1]) * 0.5
    return WeightedPitchPDF(
        bin_edges=bin_edges,
        density=density,
        bin_centers=bin_centers,
        bin_size=bin_size,
        total_weight=total_weight,
    )
def compute_strain_zones(
    range_min: float,
    range_max: float,
    comfort_band: Tuple[float, float],
    comfort_center: float,
    variance: float,
    *,
    variance_threshold: Optional[float] = 1.5,
) -> Tuple[StrainZone, ...]:
    """Derive strain zones from comfort band and distribution spread.
    The primary strain zones are below/above the comfort band. If the
    distribution standard deviation exceeds `variance_threshold` (in MIDI
    units), an additional high-variance zone around the comfort center is
    reported.
    """
    zones: list[StrainZone] = []
    comfort_low, comfort_high = comfort_band
    if range_min < comfort_low:
        zones.append(
            StrainZone(
                label="low",
                low=range_min,
                high=comfort_low,
                reason="below comfort band",
            )
        )
    if range_max > comfort_high:
        zones.append(
            StrainZone(
                label="high",
                low=comfort_high,
                high=range_max,
                reason="above comfort band",
            )
        )
    if variance_threshold is not None:
        std_dev = math.sqrt(max(variance, 0.0))
        if std_dev >= variance_threshold:
            zones.append(
                StrainZone(
                    label="high_variance",
                    low=comfort_center - std_dev,
                    high=comfort_center + std_dev,
                    reason="high distribution spread",
                )
            )
    return tuple(zones)
def analyze_tessitura(
    pitches: Sequence[float],
    weights: Optional[Sequence[float]] = None,
    confidences: Optional[Sequence[float]] = None,
    uncertainties: Optional[Sequence[float]] = None,
    *,
    tessitura_percentiles: Tuple[float, float] = (0.15, 0.85),
    comfort_occupancy: float = 0.7,
    histogram_bin_size: float = 0.1,
    return_pdf: bool = False,
    strain_variance_threshold: Optional[float] = 1.5,
) -> TessituraAnalysis:
    """Analyze tessitura metrics from weighted pitch observations.
    Args:
        pitches: Sequence of MIDI pitch values.
        weights: Optional per-observation weights.
        confidences: Optional per-observation confidences multiplied into weights.
        uncertainties: Optional per-observation uncertainties (MIDI units).
        tessitura_percentiles: Lower/upper percentiles for tessitura band.
        comfort_occupancy: Occupancy fraction for comfort band (default 70%).
        histogram_bin_size: Bin size for optional PDF output.
        return_pdf: Whether to compute and return the weighted PDF.
        strain_variance_threshold: Std-dev threshold for high-variance strain zone.
    Returns:
        TessituraAnalysis containing metrics and an optional PDF.
    """
    values, weight_values, uncertainty_values = _prepare_observations(
        pitches,
        weights=weights,
        confidences=confidences,
        uncertainties=uncertainties,
    )
    weight_sum = float(np.sum(weight_values))
    if weight_sum <= 0:
        raise ValueError("Total weight must be positive.")
    comfort_center = float(np.sum(values * weight_values) / weight_sum)
    variance = float(np.sum(weight_values * (values - comfort_center) ** 2) / weight_sum)
    std_dev = float(math.sqrt(max(variance, 0.0)))
    # Variance of weighted mean under fixed-weight assumption: Σ(w_i² σ_i²) / (Σw_i)²
    # Note: this formula is exact when weights are fixed constants; if weights were
    # inverse-variance optimal (w_i ∝ 1/σ_i²), use 1/Σ(1/σ_i²) instead.
    mean_variance = float(
        np.sum((weight_values**2) * (uncertainty_values**2))
        / max(weight_sum**2, np.finfo(float).eps)
    )
    range_min, range_max = compute_range(values, weights=weight_values)
    tessitura_band = compute_weighted_percentiles(
        values, weights=weight_values, percentiles=tessitura_percentiles
    )
    comfort_band = compute_comfort_band(
        values, weights=weight_values, occupancy=comfort_occupancy
    )
    strain_zones = compute_strain_zones(
        range_min,
        range_max,
        comfort_band,
        comfort_center,
        variance,
        variance_threshold=strain_variance_threshold,
    )
    pdf = (
        compute_weighted_pdf(
            values,
            weights=weight_values,
            confidences=None,
            bin_size=histogram_bin_size,
        )
        if return_pdf
        else None
    )
    metrics = TessituraMetrics(
        count=int(values.size),
        weight_sum=weight_sum,
        range_min=range_min,
        range_max=range_max,
        tessitura_band=tessitura_band,
        comfort_band=comfort_band,
        comfort_center=comfort_center,
        variance=variance,
        std_dev=std_dev,
        mean_variance=mean_variance,
        strain_zones=strain_zones,
    )
    return TessituraAnalysis(metrics=metrics, pdf=pdf)
