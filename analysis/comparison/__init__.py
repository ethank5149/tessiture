"""Comparison analysis package — metrics for vocalist-vs-reference evaluation."""
from analysis.comparison.pitch_comparison import compare_pitch_tracks, PitchComparisonResult
from analysis.comparison.rhythm_comparison import compare_note_timing, RhythmComparisonResult
from analysis.comparison.range_comparison import compare_vocal_ranges, RangeComparisonResult
from analysis.comparison.formant_comparison import compare_formants, FormantComparisonResult
from analysis.comparison.alignment import align_to_reference
from analysis.comparison.reference_cache import ReferenceCache, ReferenceAnalysis
from analysis.comparison.session_report import (
    SessionReport,
    build_session_report,
    session_report_to_dict,
)

__all__ = [
    "compare_pitch_tracks", "PitchComparisonResult",
    "compare_note_timing", "RhythmComparisonResult",
    "compare_vocal_ranges", "RangeComparisonResult",
    "compare_formants", "FormantComparisonResult",
    "align_to_reference",
    "ReferenceCache", "ReferenceAnalysis",
    "SessionReport", "build_session_report", "session_report_to_dict",
]
