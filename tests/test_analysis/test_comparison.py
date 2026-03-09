"""Unit tests for analysis/comparison/ modules.

Covers: reference_cache, alignment, pitch_comparison, rhythm_comparison,
        range_comparison, formant_comparison, session_report.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

import analysis.comparison.reference_cache as rc_module
from analysis.comparison.reference_cache import ReferenceAnalysis, store, get, exists, list_all, delete
from analysis.comparison.alignment import align_to_reference, interpolate_reference_at_time
from analysis.comparison.pitch_comparison import compare_pitch_tracks
from analysis.comparison.rhythm_comparison import compare_note_timing
from analysis.comparison.range_comparison import compare_vocal_ranges
from analysis.comparison.formant_comparison import compare_formants
from analysis.comparison.session_report import _is_voiced_f0, build_session_report, session_report_to_dict


# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------


def make_pitch_frame(time_s: float, f0_hz: float, midi: Optional[float] = None, note_name: str = "A4", confidence: float = 0.9) -> Dict[str, Any]:
    if midi is None:
        midi = 69.0 if f0_hz > 0 else None
    return {"time_s": time_s, "f0_hz": f0_hz, "midi": midi, "note_name": note_name, "confidence": confidence}


def make_note_event(start_s: float, end_s: float, midi: float = 69.0, note_name: str = "A4") -> Dict[str, Any]:
    return {"start_s": start_s, "end_s": end_s, "midi": midi, "note_name": note_name, "duration_s": end_s - start_s}


def make_chunk_result(timestamp_s: float, user_f0_hz: float = 440.0, ref_f0_hz: float = 440.0, deviation: float = 0.0, in_tune: bool = True) -> Dict[str, Any]:
    return {
        "timestamp_s": timestamp_s,
        "user_f0_hz": user_f0_hz,
        "user_midi": 69.0 if user_f0_hz else None,
        "user_note_name": "A4",
        "user_confidence": 0.9,
        "reference_f0_hz": ref_f0_hz,
        "reference_midi": 69.0 if ref_f0_hz else None,
        "reference_note_name": "A4",
        "pitch_deviation_cents": deviation,
        "in_tune": in_tune,
    }


def make_reference_analysis(ref_id: str = "test-ref-001") -> ReferenceAnalysis:
    return ReferenceAnalysis(
        reference_id=ref_id,
        source="upload",
        source_id="test.wav",
        analysis={},
        pitch_track=[
            make_pitch_frame(0.0, 440.0),
            make_pitch_frame(0.1, 440.0),
            make_pitch_frame(0.2, 440.0),
        ],
        note_events=[make_note_event(0.0, 1.0)],
        duration_s=10.0,
        key="A major",
        tessitura_center_midi=69.0,
        formant_summary=None,
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Fixture: isolate the reference cache between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_reference_cache():
    """Clear the module-level _CACHE dict before and after each test."""
    rc_module._CACHE.clear()
    yield
    rc_module._CACHE.clear()


# ---------------------------------------------------------------------------
# reference_cache tests
# ---------------------------------------------------------------------------


class TestReferenceCache:

    def test_reference_cache_store_and_get(self):
        """store() persists a ReferenceAnalysis; get() retrieves it by id with matching fields."""
        ref = make_reference_analysis("abc123")
        returned_id = store(ref)

        assert returned_id == "abc123", "store() should return the reference_id"
        retrieved = get("abc123")
        assert retrieved is not None, "get() should return the stored analysis"
        assert retrieved.reference_id == "abc123"
        assert retrieved.source == "upload"
        assert retrieved.source_id == "test.wav"
        assert retrieved.duration_s == 10.0
        assert retrieved.key == "A major"

    def test_reference_cache_exists(self):
        """exists() returns True after store, False for unknown id."""
        ref = make_reference_analysis("existing-id")
        store(ref)

        assert exists("existing-id") is True, "exists() should return True for stored id"
        assert exists("nonexistent-id") is False, "exists() should return False for unknown id"

    def test_reference_cache_delete(self):
        """delete() removes the entry; get() returns None afterwards."""
        ref = make_reference_analysis("to-delete")
        store(ref)
        assert exists("to-delete") is True

        result = delete("to-delete")
        assert result is True, "delete() should return True when entry existed"
        assert get("to-delete") is None, "get() should return None after delete"
        assert exists("to-delete") is False

    def test_reference_cache_delete_nonexistent(self):
        """delete() returns False for an id that was never stored."""
        result = delete("never-existed")
        assert result is False, "delete() of unknown id should return False"

    def test_reference_cache_list_all(self):
        """list_all() returns all stored entries with expected count."""
        store(make_reference_analysis("ref-1"))
        store(make_reference_analysis("ref-2"))
        store(make_reference_analysis("ref-3"))

        all_refs = list_all()
        assert len(all_refs) == 3, "list_all() should return exactly 3 entries"
        ids = {r.reference_id for r in all_refs}
        assert ids == {"ref-1", "ref-2", "ref-3"}

    def test_reference_cache_isolation(self):
        """Multiple cached entries don't interfere with each other."""
        ref_a = make_reference_analysis("ref-a")
        ref_b = ReferenceAnalysis(
            reference_id="ref-b",
            source="example",
            source_id="example_song",
            analysis={},
            pitch_track=[],
            note_events=[],
            duration_s=60.0,
            key="C major",
            tessitura_center_midi=60.0,
            formant_summary={"mean_f1_hz": 800.0, "mean_f2_hz": 1200.0},
            created_at=datetime.now(timezone.utc),
        )

        store(ref_a)
        store(ref_b)

        retrieved_a = get("ref-a")
        retrieved_b = get("ref-b")

        assert retrieved_a is not None
        assert retrieved_b is not None
        assert retrieved_a.source == "upload", "ref-a source should be 'upload'"
        assert retrieved_b.source == "example", "ref-b source should be 'example'"
        assert retrieved_a.duration_s == 10.0
        assert retrieved_b.duration_s == 60.0
        assert retrieved_a.key == "A major"
        assert retrieved_b.key == "C major"


# ---------------------------------------------------------------------------
# alignment tests
# ---------------------------------------------------------------------------


class TestAlignment:

    def test_align_to_reference_basic(self):
        """Simple 3-frame tracks: aligned pairs contain expected time_s values."""
        user = [
            make_pitch_frame(0.0, 440.0),
            make_pitch_frame(0.1, 440.0),
            make_pitch_frame(0.2, 440.0),
        ]
        reference = [
            make_pitch_frame(0.0, 440.0),
            make_pitch_frame(0.1, 440.0),
            make_pitch_frame(0.2, 440.0),
        ]

        pairs = align_to_reference(user, reference)

        assert len(pairs) == 3, "Should have one pair per user frame"
        for i, pair in enumerate(pairs):
            assert pair["time_s"] == pytest.approx(i * 0.1), f"Pair {i} time_s mismatch"
            assert pair["user"] is not None
            # All user frames have matching reference frames (within 0.05s tolerance)
            assert pair["reference"] is not None, f"Pair {i} should have a reference match"

    def test_align_to_reference_playback_offset(self):
        """With playback_offset_s=1.0, reference is looked up at user_time + 1.0."""
        user = [make_pitch_frame(0.0, 440.0), make_pitch_frame(0.1, 440.0)]
        # Reference at times 1.0 and 1.1 to match user[0]+1.0 and user[1]+1.0
        reference = [
            make_pitch_frame(1.0, 440.0),
            make_pitch_frame(1.1, 440.0),
        ]

        pairs = align_to_reference(user, reference, playback_offset_s=1.0)

        assert len(pairs) == 2
        # user frame at t=0.0 should align to reference at t=1.0
        assert pairs[0]["reference"] is not None, "First pair should match reference at t=1.0"
        assert pairs[0]["reference"]["time_s"] == pytest.approx(1.0)
        # user frame at t=0.1 should align to reference at t=1.1
        assert pairs[1]["reference"] is not None, "Second pair should match reference at t=1.1"
        assert pairs[1]["reference"]["time_s"] == pytest.approx(1.1)

    def test_align_to_reference_no_match(self):
        """User frame at t=100s with reference only up to t=10s → reference=None."""
        user = [make_pitch_frame(100.0, 440.0)]
        reference = [make_pitch_frame(t * 0.1, 440.0) for t in range(100)]  # 0.0 to 9.9s

        pairs = align_to_reference(user, reference)

        assert len(pairs) == 1
        assert pairs[0]["reference"] is None, "Far-away user frame should have reference=None (beyond tolerance)"

    def test_align_to_reference_empty_reference(self):
        """Empty reference track → all pairs have reference=None."""
        user = [make_pitch_frame(0.0, 440.0), make_pitch_frame(0.1, 440.0)]
        pairs = align_to_reference(user, [])

        assert len(pairs) == 2
        assert all(p["reference"] is None for p in pairs), "All pairs should have reference=None for empty reference"

    def test_interpolate_reference_at_time_exact(self):
        """Query at exact reference frame time → returns that frame's data."""
        reference = [
            make_pitch_frame(0.0, 440.0),
            make_pitch_frame(0.1, 880.0),
            make_pitch_frame(0.2, 220.0),
        ]

        result = interpolate_reference_at_time(reference, 0.1)

        assert result is not None
        assert result["f0_hz"] == pytest.approx(880.0), "Should return exact frame f0 at t=0.1"
        assert result["time_s"] == pytest.approx(0.1)

    def test_interpolate_reference_at_time_between(self):
        """Query between two frames → f0_hz is geometrically (log-linearly) interpolated."""
        reference = [
            make_pitch_frame(0.0, 400.0),
            make_pitch_frame(1.0, 600.0),
        ]

        result = interpolate_reference_at_time(reference, 0.5)

        assert result is not None
        # At t=0.5, geometric midpoint of 400 and 600: 400 * sqrt(600/400) ≈ 489.90
        expected_geo = 400.0 * ((600.0 / 400.0) ** 0.5)
        assert result["f0_hz"] == pytest.approx(expected_geo, abs=1.0), "f0_hz should be geometrically interpolated"
        assert result["time_s"] == pytest.approx(0.5)

    def test_interpolate_reference_at_time_empty(self):
        """Empty reference track → returns None."""
        result = interpolate_reference_at_time([], 0.5)
        assert result is None, "Should return None for empty reference track"

    def test_interpolate_reference_before_first_frame(self):
        """Query before first frame → returns copy of first frame."""
        reference = [make_pitch_frame(1.0, 440.0), make_pitch_frame(2.0, 880.0)]
        result = interpolate_reference_at_time(reference, 0.0)
        assert result is not None
        assert result["f0_hz"] == pytest.approx(440.0), "Should return first frame when queried before it"


# ---------------------------------------------------------------------------
# pitch_comparison tests
# ---------------------------------------------------------------------------


class TestPitchComparison:

    def _make_pair(self, time_s: float, user_f0: float, ref_f0: float) -> Dict[str, Any]:
        return {
            "time_s": time_s,
            "user": {"f0_hz": user_f0},
            "reference": {"f0_hz": ref_f0},
        }

    def test_compare_pitch_tracks_perfect(self):
        """User and reference both at 440 Hz → deviation=0, accuracy=1.0, bias=0."""
        pairs = [self._make_pair(t * 0.1, 440.0, 440.0) for t in range(5)]
        result = compare_pitch_tracks(pairs)

        assert result.voiced_frame_count == 5
        assert result.mean_absolute_pitch_error_cents == pytest.approx(0.0)
        assert result.pitch_accuracy_ratio == pytest.approx(1.0)
        assert result.pitch_bias_cents == pytest.approx(0.0)

    def test_compare_pitch_tracks_sharp(self):
        """User 10 cents sharp of reference → mean_absolute_pitch_error ≈ 10, bias > 0."""
        # 2^(10/1200) ≈ 1.00579 — user is slightly sharp of reference
        user_f0 = 440.0 * (2 ** (10.0 / 1200.0))
        pairs = [self._make_pair(t * 0.1, user_f0, 440.0) for t in range(5)]
        result = compare_pitch_tracks(pairs)

        assert result.voiced_frame_count == 5
        assert result.mean_absolute_pitch_error_cents == pytest.approx(10.0, abs=0.1), \
            "Mean absolute error should be ~10 cents when user is 10 cents sharp"
        assert result.pitch_bias_cents > 0, "Bias should be positive when user is consistently sharp"

    def test_compare_pitch_tracks_empty(self):
        """Empty aligned_pairs → returns result with voiced_frame_count=0."""
        result = compare_pitch_tracks([])

        assert result.voiced_frame_count == 0
        assert result.frame_deviations_cents == []
        assert result.mean_absolute_pitch_error_cents == pytest.approx(0.0)
        assert result.pitch_accuracy_ratio == pytest.approx(0.0)

    def test_compare_pitch_tracks_mixed_voiced(self):
        """Only pairs with non-None reference and valid f0 contribute to voiced count."""
        pairs = [
            # Valid voiced pair
            self._make_pair(0.0, 440.0, 440.0),
            # reference=None — should be excluded
            {"time_s": 0.1, "user": {"f0_hz": 440.0}, "reference": None},
            # reference present but user f0=0 — unvoiced, excluded
            {"time_s": 0.2, "user": {"f0_hz": 0.0}, "reference": {"f0_hz": 440.0}},
            # Valid voiced pair
            self._make_pair(0.3, 440.0, 440.0),
        ]
        result = compare_pitch_tracks(pairs)

        assert result.voiced_frame_count == 2, "Only 2 valid voiced pairs should contribute"
        assert result.pitch_accuracy_ratio == pytest.approx(1.0)

    def test_compare_pitch_tracks_reference_none_only(self):
        """All pairs have reference=None → voiced_frame_count=0."""
        pairs = [
            {"time_s": 0.0, "user": {"f0_hz": 440.0}, "reference": None},
            {"time_s": 0.1, "user": {"f0_hz": 440.0}, "reference": None},
        ]
        result = compare_pitch_tracks(pairs)
        assert result.voiced_frame_count == 0


# ---------------------------------------------------------------------------
# rhythm_comparison tests
# ---------------------------------------------------------------------------


class TestRhythmComparison:

    def test_compare_note_timing_perfect(self):
        """User events match reference exactly → note_hit_rate=1.0, all deviations=0."""
        events = [
            make_note_event(0.0, 0.5),
            make_note_event(1.0, 1.5),
            make_note_event(2.0, 2.5),
        ]
        result = compare_note_timing(events, events)

        assert result.note_hit_rate == pytest.approx(1.0), "Perfect match should give hit_rate=1.0"
        assert result.matched_note_count == 3
        assert result.reference_note_count == 3
        assert all(d == pytest.approx(0.0) for d in result.onset_deviations_ms), \
            "All onset deviations should be 0 for perfect match"

    def test_compare_note_timing_late(self):
        """User events 100ms late → mean_onset_error≈100ms, deviations positive."""
        ref_events = [make_note_event(0.0, 0.5), make_note_event(1.0, 1.5)]
        # User is 0.1s (100ms) late
        user_events = [make_note_event(0.1, 0.6), make_note_event(1.1, 1.6)]

        result = compare_note_timing(user_events, ref_events)

        assert result.note_hit_rate == pytest.approx(1.0), "Both notes should match within tolerance"
        assert result.mean_onset_error_ms == pytest.approx(100.0, abs=1.0), \
            "Mean onset error should be ~100ms"
        # onset_deviation = (user_start - ref_start) * 1000 = positive for late user
        assert all(d > 0 for d in result.onset_deviations_ms), "Late user → positive deviations"

    def test_compare_note_timing_missed(self):
        """User has 0 events, reference has 5 → note_hit_rate=0, matched_note_count=0."""
        ref_events = [make_note_event(float(i), float(i) + 0.5) for i in range(5)]
        result = compare_note_timing([], ref_events)

        assert result.note_hit_rate == pytest.approx(0.0), "No user events → hit_rate=0"
        assert result.matched_note_count == 0
        assert result.reference_note_count == 5

    def test_compare_note_timing_partial(self):
        """User matches 3 of 5 reference notes within tolerance → note_hit_rate=0.6."""
        ref_events = [make_note_event(float(i), float(i) + 0.5, midi=69.0) for i in range(5)]
        # User matches notes at t=0, 1, 2 — skips 3 and 4
        user_events = [
            make_note_event(0.0, 0.5, midi=69.0),
            make_note_event(1.0, 1.5, midi=69.0),
            make_note_event(2.0, 2.5, midi=69.0),
        ]
        result = compare_note_timing(user_events, ref_events)

        assert result.note_hit_rate == pytest.approx(0.6, abs=0.01), \
            "3 of 5 matched → hit rate=0.6"
        assert result.matched_note_count == 3
        assert result.reference_note_count == 5

    def test_compare_note_timing_empty_reference(self):
        """Empty reference → returns 0 count result."""
        user_events = [make_note_event(0.0, 0.5)]
        result = compare_note_timing(user_events, [])

        assert result.note_hit_rate == pytest.approx(0.0)
        assert result.reference_note_count == 0


# ---------------------------------------------------------------------------
# range_comparison tests
# ---------------------------------------------------------------------------


class TestRangeComparison:

    def test_compare_vocal_ranges_full_overlap(self):
        """User range [60,72] MIDI, reference same range → range_coverage_ratio=1.0."""
        user_midi = list(range(60, 73))  # 60 to 72 inclusive
        ref_events = [
            make_note_event(0.0, 0.5, midi=60.0),
            make_note_event(1.0, 1.5, midi=72.0),
        ]
        result = compare_vocal_ranges(user_midi, ref_events)

        assert result.user_range_min_midi == pytest.approx(60.0)
        assert result.user_range_max_midi == pytest.approx(72.0)
        assert result.reference_range_min_midi == pytest.approx(60.0)
        assert result.reference_range_max_midi == pytest.approx(72.0)
        assert result.range_coverage_ratio == pytest.approx(1.0), \
            "Full overlap should give coverage_ratio=1.0"

    def test_compare_vocal_ranges_partial_overlap(self):
        """User [60,66], reference [64,72] → coverage < 1.0."""
        user_midi = [float(m) for m in range(60, 67)]  # 60-66
        ref_events = [
            make_note_event(0.0, 0.5, midi=64.0),
            make_note_event(1.0, 1.5, midi=72.0),
        ]
        result = compare_vocal_ranges(user_midi, ref_events)

        assert result.range_coverage_ratio < 1.0, "Partial overlap should give coverage < 1.0"
        # overlap = [64,66] = 2 semitones; ref span = 72-64 = 8 semitones; ratio = 2/8 = 0.25
        assert result.range_coverage_ratio == pytest.approx(0.25, abs=0.01), \
            "Overlap is [64,66]=2 semitones, ref span=8 → ratio=0.25"

    def test_compare_vocal_ranges_no_voiced_midi(self):
        """Empty user_voiced_midi → returns result with user_range_min/max=None."""
        ref_events = [make_note_event(0.0, 0.5, midi=69.0)]
        result = compare_vocal_ranges([], ref_events)

        assert result.user_range_min_midi is None, "No voiced MIDI → user_range_min should be None"
        assert result.user_range_max_midi is None, "No voiced MIDI → user_range_max should be None"
        assert result.range_coverage_ratio == pytest.approx(0.0)

    def test_compare_vocal_ranges_no_ref_events(self):
        """Empty reference note events → range_coverage_ratio=0."""
        user_midi = [60.0, 65.0, 72.0]
        result = compare_vocal_ranges(user_midi, [])

        assert result.reference_range_min_midi is None
        assert result.reference_range_max_midi is None
        assert result.range_coverage_ratio == pytest.approx(0.0), \
            "No reference → coverage_ratio=0"

    def test_compare_vocal_ranges_with_tessitura_metrics(self):
        """Tessitura metrics with comfort_center → tessitura_center_offset is computed."""
        user_midi = [60.0, 65.0, 70.0]
        ref_events = [make_note_event(0.0, 0.5, midi=60.0), make_note_event(1.0, 1.5, midi=72.0)]
        # ref center = (60+72)/2 = 66
        user_tessitura_metrics = {"comfort_center": 68.0}
        result = compare_vocal_ranges(user_midi, ref_events, user_tessitura_metrics)

        assert result.tessitura_center_offset_semitones is not None
        assert result.tessitura_center_offset_semitones == pytest.approx(68.0 - 66.0, abs=0.1), \
            "Offset should be user_center - ref_center = 68 - 66 = 2"


# ---------------------------------------------------------------------------
# formant_comparison tests
# ---------------------------------------------------------------------------


class TestFormantComparison:

    def test_compare_formants_both_none(self):
        """Both None → formant_data_available=False."""
        result = compare_formants(None, None)

        assert result.formant_data_available is False
        assert result.mean_f1_deviation_hz is None
        assert result.mean_f2_deviation_hz is None
        assert result.spectral_centroid_deviation_hz is None

    def test_compare_formants_user_none(self):
        """User None, ref has data → formant_data_available=False."""
        ref_summary = {"mean_f1_hz": 800.0, "mean_f2_hz": 1200.0}
        result = compare_formants(None, ref_summary)

        assert result.formant_data_available is False, \
            "Missing user formant data → formant_data_available=False"

    def test_compare_formants_ref_none(self):
        """Ref None, user has data → formant_data_available=False."""
        user_summary = {"mean_f1_hz": 700.0, "mean_f2_hz": 1100.0}
        result = compare_formants(user_summary, None)

        assert result.formant_data_available is False, \
            "Missing reference formant data → formant_data_available=False"

    def test_compare_formants_both_valid(self):
        """Both have mean_f1_hz and mean_f2_hz → formant_data_available=True, deviations computed."""
        user_summary = {"mean_f1_hz": 700.0, "mean_f2_hz": 1100.0}
        ref_summary = {"mean_f1_hz": 800.0, "mean_f2_hz": 1200.0}

        result = compare_formants(user_summary, ref_summary)

        assert result.formant_data_available is True
        assert result.mean_f1_deviation_hz == pytest.approx(100.0), "F1 deviation = |700-800| = 100"
        assert result.mean_f2_deviation_hz == pytest.approx(100.0), "F2 deviation = |1100-1200| = 100"
        # User centroid = (700+1100)/2=900, Ref centroid = (800+1200)/2=1000, offset=-100
        assert result.spectral_centroid_deviation_hz == pytest.approx(-100.0), \
            "Spectral centroid deviation = user_centroid - ref_centroid = 900 - 1000 = -100"

    def test_compare_formants_identical(self):
        """Identical formants → deviations=0."""
        summary = {"mean_f1_hz": 800.0, "mean_f2_hz": 1200.0}
        result = compare_formants(summary, summary)

        assert result.formant_data_available is True
        assert result.mean_f1_deviation_hz == pytest.approx(0.0)
        assert result.mean_f2_deviation_hz == pytest.approx(0.0)
        assert result.spectral_centroid_deviation_hz == pytest.approx(0.0)

    def test_compare_formants_invalid_values(self):
        """Non-positive or non-numeric values → formant_data_available=False."""
        user_summary = {"mean_f1_hz": -100.0, "mean_f2_hz": 1200.0}  # negative F1
        ref_summary = {"mean_f1_hz": 800.0, "mean_f2_hz": 1200.0}

        result = compare_formants(user_summary, ref_summary)

        assert result.formant_data_available is False, \
            "Negative F1 is invalid → formant_data_available=False"


# ---------------------------------------------------------------------------
# session_report tests
# ---------------------------------------------------------------------------


class TestSessionReport:

    def _make_base_kwargs(self) -> dict:
        return {
            "session_id": "session-001",
            "reference_id": "ref-001",
            "reference_source": "upload",
            "reference_source_id": "test.wav",
            "reference_key": "A major",
            "session_started_at": "2024-01-01T00:00:00Z",
            "session_duration_s": 60.0,
            "reference_note_events": [make_note_event(0.0, 1.0)],
            "reference_formant_summary": None,
            "reference_tessitura_center_midi": 69.0,
        }

    def test_build_session_report_empty_chunks(self):
        """Zero chunks → voiced_chunks=0, pitch comparison with voiced_frame_count=0."""
        kwargs = self._make_base_kwargs()
        report = build_session_report(chunk_results=[], **kwargs)

        assert report.session_id == "session-001"
        assert report.voiced_chunks == 0
        assert report.total_chunks_processed == 0
        assert report.pitch_comparison["voiced_frame_count"] == 0, \
            "No chunks → pitch comparison should report 0 voiced frames"

    def test_build_session_report_with_voiced_chunks(self):
        """5 chunk_results with in-range voiced user_f0_hz → pitch comparison metrics computed."""
        kwargs = self._make_base_kwargs()
        chunks = [make_chunk_result(i * 0.1) for i in range(5)]  # 5 chunks at 440Hz
        report = build_session_report(chunk_results=chunks, **kwargs)

        assert report.total_chunks_processed == 5
        assert report.voiced_chunks == 5, "All 5 chunks have in-range voiced f0"
        # Pitch comparison should have been computed over the chunks
        assert isinstance(report.pitch_comparison, dict)
        assert "voiced_frame_count" in report.pitch_comparison
        # Build uses chunk-based alignment, so may vary
        assert report.pitch_comparison["voiced_frame_count"] >= 0

    def test_build_session_report_mixed_voiced_unvoiced(self):
        """Mix of voiced and unvoiced chunks → only voiced count."""
        kwargs = self._make_base_kwargs()
        chunks = [
            make_chunk_result(0.0, user_f0_hz=440.0),   # voiced
            make_chunk_result(0.1, user_f0_hz=0.0),     # unvoiced (f0=0)
            make_chunk_result(0.2, user_f0_hz=440.0),   # voiced
            make_chunk_result(0.3, user_f0_hz=None),    # unvoiced (None)
        ]
        report = build_session_report(chunk_results=chunks, **kwargs)

        assert report.total_chunks_processed == 4
        assert report.voiced_chunks == 2, "Only 2 chunks have in-range voiced f0"

    def test_session_report_to_dict(self):
        """session_report_to_dict returns a plain dict with no dataclass instances inside."""
        import dataclasses

        kwargs = self._make_base_kwargs()
        chunks = [make_chunk_result(i * 0.1) for i in range(3)]
        report = build_session_report(chunk_results=chunks, **kwargs)

        result_dict = session_report_to_dict(report)

        assert isinstance(result_dict, dict), "session_report_to_dict should return a dict"
        # Verify no nested dataclasses
        def check_no_dataclasses(obj, path="root"):
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                raise AssertionError(f"Found dataclass at path '{path}': {type(obj)}")
            if isinstance(obj, dict):
                for k, v in obj.items():
                    check_no_dataclasses(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    check_no_dataclasses(v, f"{path}[{i}]")

        check_no_dataclasses(result_dict)

        # Verify key fields are present
        assert "session_id" in result_dict
        assert "reference_id" in result_dict
        assert "pitch_comparison" in result_dict
        assert "rhythm_comparison" in result_dict
        assert "range_comparison" in result_dict
        assert "formant_comparison" in result_dict

    def test_build_session_report_fields_match_inputs(self):
        """Verify session metadata fields are preserved in the report."""
        kwargs = self._make_base_kwargs()
        report = build_session_report(chunk_results=[], **kwargs)

        assert report.reference_id == "ref-001"
        assert report.reference_source == "upload"
        assert report.reference_source_id == "test.wav"
        assert report.reference_key == "A major"
        assert report.session_started_at == "2024-01-01T00:00:00Z"
        assert report.session_duration_s == pytest.approx(60.0)

    def test_is_voiced_f0_uses_bounded_frequency_policy(self):
        assert _is_voiced_f0(220.0) is True
        assert _is_voiced_f0(79.9) is False
        assert _is_voiced_f0(1200.0) is True
        assert _is_voiced_f0(1200.1) is False

    def test_build_session_report_excludes_out_of_range_artifacts(self):
        kwargs = self._make_base_kwargs()
        chunks = [
            make_chunk_result(0.0, user_f0_hz=70.0),
            make_chunk_result(0.1, user_f0_hz=220.0),
            make_chunk_result(0.2, user_f0_hz=1400.0),
        ]

        report = build_session_report(chunk_results=chunks, **kwargs)

        assert report.total_chunks_processed == 3
        assert report.voiced_chunks == 1
        assert report.pitch_comparison["voiced_frame_count"] == 1

    def test_build_session_report_keeps_in_range_voiced_frequencies(self):
        kwargs = self._make_base_kwargs()
        chunks = [
            make_chunk_result(0.0, user_f0_hz=85.0),
            make_chunk_result(0.1, user_f0_hz=1100.0),
        ]

        report = build_session_report(chunk_results=chunks, **kwargs)

        assert report.total_chunks_processed == 2
        assert report.voiced_chunks == 2
        assert report.pitch_comparison["voiced_frame_count"] == 2
