"""Tessitura analysis package."""

from analysis.tessitura.analyzer import (
    StrainZone,
    TessituraAnalysis,
    TessituraMetrics,
    WeightedPitchPDF,
    analyze_tessitura,
    compute_strain_zones,
    compute_weighted_pdf,
)
from analysis.tessitura.vocal_range import (
    compute_comfort_band,
    compute_extremum_confidence_intervals,
    compute_range,
    compute_weighted_percentiles,
)

__all__ = [
    "StrainZone",
    "TessituraAnalysis",
    "TessituraMetrics",
    "WeightedPitchPDF",
    "analyze_tessitura",
    "compute_comfort_band",
    "compute_extremum_confidence_intervals",
    "compute_range",
    "compute_strain_zones",
    "compute_weighted_pdf",
    "compute_weighted_percentiles",
]
