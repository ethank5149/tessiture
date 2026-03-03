import json
import numpy as np

from analysis.advanced.phrase_segmentation import (
    compute_energy_envelope,
    segment_phrases_from_energy,
)
from analysis.advanced.vibrato import detect_vibrato
from analysis.tessitura.analyzer import analyze_tessitura
from calibration.models.confidence_models import (
    build_confidence_surface,
    suggest_detection_thresholds,
)
from calibration.monte_carlo.uncertainty_analyzer import summarize_uncertainty
from calibration.reference_generation.lhs_sampler import lhs_sample
from calibration.reference_generation.signal_generator import generate_synthetic_signal
from reporting.csv_generator import generate_csv_report
from reporting.json_generator import generate_json_report
from reporting.pdf_composer import _event_confidence, _event_start
from reporting.visualization import plot_key_stability, plot_piano_roll


def test_analyze_tessitura_returns_metrics_and_pdf() -> None:
    pitches = [60.0, 62.0, 64.0, 65.0, 67.0, 69.0]
    weights = [0.8, 0.9, 1.0, 1.0, 0.9, 0.8]

    result = analyze_tessitura(pitches, weights=weights, return_pdf=True)

    assert result.metrics.count == len(pitches)
    assert result.metrics.range_max >= result.metrics.range_min
    assert result.pdf is not None
    assert result.pdf.density.size > 0


def test_detect_vibrato_finds_periodic_modulation() -> None:
    # Build an f0 trajectory with ~5 Hz modulation sampled at frame rate 100 Hz.
    frame_rate = 100.0
    sample_rate = 44100
    hop_length = int(round(sample_rate / frame_rate))
    t = np.arange(300, dtype=float) / frame_rate
    f0 = 220.0 * (2.0 ** ((30.0 * np.sin(2.0 * np.pi * 5.0 * t)) / 1200.0))

    features = detect_vibrato(f0, sample_rate=sample_rate, hop_length=hop_length)

    assert features.valid
    assert 3.0 <= features.rate_hz <= 8.0
    assert features.depth_cents > 0.0


def test_phrase_segmentation_detects_pause_boundaries() -> None:
    # Two voiced regions separated by a low-energy pause.
    energy = np.array([1.0] * 20 + [0.001] * 12 + [0.9] * 20, dtype=float)
    sample_rate = 1000
    hop_length = 10

    result = segment_phrases_from_energy(
        energy,
        sample_rate=sample_rate,
        hop_length=hop_length,
        energy_floor_db=-20.0,
        min_pause_s=0.05,
        min_phrase_s=0.05,
    )

    assert result.boundaries
    kinds = [b.kind for b in result.boundaries]
    assert "start" in kinds and "end" in kinds


def test_compute_energy_envelope_non_empty() -> None:
    sample_rate = 8000
    tone = np.sin(2.0 * np.pi * 220.0 * np.arange(sample_rate) / sample_rate).astype(np.float32)

    energy, times = compute_energy_envelope(tone, sample_rate, frame_length=256, hop_length=128)

    assert energy.size > 0
    assert energy.size == times.size


def test_confidence_surface_and_threshold_suggestion() -> None:
    freq_bins = np.array([100.0, 200.0, 400.0], dtype=float)
    snr_bins = np.array([0.0, 10.0, 20.0], dtype=float)
    probs = np.array(
        [
            [0.2, 0.4, 0.6],
            [0.3, 0.6, 0.8],
            [0.4, 0.7, 0.9],
        ],
        dtype=float,
    )

    surface = build_confidence_surface(freq_bins, snr_bins, probs)
    query = surface(np.array([150.0, 300.0]), np.array([5.0, 15.0]))
    thresholds = suggest_detection_thresholds(surface)

    assert query.shape == (2,)
    assert np.all(query >= 0.0)
    assert "min_confidence" in thresholds


def test_uncertainty_summary_contains_expected_keys() -> None:
    results = [
        {
            "metadata": {"note_frequencies_hz": [220.0, 330.0, 440.0]},
            "pitch_error_cents": [2.0, -1.0, 0.5],
        }
    ]

    summary = summarize_uncertainty(results)

    assert "pitch_bias_cents" in summary
    assert "pitch_variance_cents2" in summary
    assert len(summary["frequency_bins_hz"]) >= 2


def test_uncertainty_summary_bin_aggregation_is_frequency_aligned() -> None:
    results = [
        {
            "metadata": {
                "note_frequencies_hz": [100.0, 100.0, 200.0, 200.0, None, "invalid"],
            },
            "pitch_error_cents": [1.0, 2.0, 10.0, 20.0, 999.0, -999.0],
        }
    ]

    summary = summarize_uncertainty(results)

    counts = np.asarray(summary["sample_counts"], dtype=int)
    bias = np.asarray(summary["pitch_bias_cents"], dtype=float)

    nonzero_bins = np.flatnonzero(counts)
    assert nonzero_bins.tolist() == [0, 11]
    assert counts[0] == 2
    assert counts[11] == 2
    assert np.isclose(bias[0], 1.5)
    assert np.isclose(bias[11], 15.0)


def test_uncertainty_summary_generated_reference_data_matches_empirical_mean_with_tolerance() -> None:
    ranges = {
        "f0_hz": (110.0, 880.0),
        "detune_cents": (-12.0, 12.0),
        "amplitude_dbfs": (-18.0, -6.0),
        "harmonic_ratio": (0.2, 0.8),
        "note_count": (1.0, 1.0),
        "duration_s": (0.1, 0.2),
        "snr_db": (30.0, 50.0),
        "vibrato_depth_cents": (0.0, 0.0),
        "vibrato_rate_hz": (5.0, 5.0),
    }
    sampled_params = lhs_sample(24, ranges, seed=20260303)

    results = []
    empirical_errors = []
    for params in sampled_params:
        _, metadata = generate_synthetic_signal(params, sample_rate=8000)
        detune = float(metadata["detune_cents"])
        error_cents = 0.9 * detune
        empirical_errors.append(error_cents)
        results.append(
            {
                "metadata": {"note_frequencies_hz": metadata["note_frequencies_hz"]},
                "pitch_error_cents": [error_cents],
            }
        )

    summary = summarize_uncertainty(results)

    counts = np.asarray(summary["sample_counts"], dtype=float)
    bias = np.asarray(summary["pitch_bias_cents"], dtype=float)
    weighted_mean = float(np.sum(counts * bias) / np.sum(counts))

    assert int(np.sum(counts)) == len(empirical_errors)
    assert np.isclose(weighted_mean, float(np.mean(empirical_errors)), atol=0.75)


def test_uncertainty_summary_analytic_canonical_cases_have_expected_bias_and_variance() -> None:
    results = [
        {
            "metadata": {"note_frequencies_hz": [100.0, 100.0, 100.0]},
            "pitch_error_cents": [-2.0, 0.0, 2.0],
        },
        {
            "metadata": {"note_frequencies_hz": [400.0, 400.0]},
            "pitch_error_cents": [10.0, 14.0],
        },
    ]

    summary = summarize_uncertainty(results)

    counts = np.asarray(summary["sample_counts"], dtype=int)
    bias = np.asarray(summary["pitch_bias_cents"], dtype=float)
    variance = np.asarray(summary["pitch_variance_cents2"], dtype=float)

    nonzero_bins = np.flatnonzero(counts)
    assert nonzero_bins.tolist() == [0, 11]
    assert counts[0] == 3
    assert counts[11] == 2
    assert np.isclose(bias[0], 0.0, atol=1e-9)
    assert np.isclose(variance[0], 8.0 / 3.0, atol=1e-9)
    assert np.isclose(bias[11], 12.0, atol=1e-9)
    assert np.isclose(variance[11], 4.0, atol=1e-9)


def test_reporting_generators_emit_expected_fields() -> None:
    payload = {
        "metadata": {"sample_rate": 44100, "hop_length": 512, "frame_rate": 86.13},
        "pitch": {
            "frames": [
                {
                    "time": 0.0,
                    "f0_hz": 220.0,
                    "midi": 57.0,
                    "note": "A3",
                    "cents": 0.0,
                    "confidence": 0.9,
                }
            ]
        },
        "chords": {"timeline": [{"start": 0.0, "end": 1.0, "label": "A:min", "confidence": 0.8}]},
        "keys": {"trajectory": [{"start": 0.0, "end": 1.0, "label": "A:min", "confidence": 0.7}]},
        "tessitura": {"metrics": {"range_min": 56.0, "range_max": 62.0, "tessitura_band": [57.0, 61.0]}},
    }

    csv_text = generate_csv_report(payload)
    json_text = generate_json_report(payload)

    assert "time,f0,note,cents,confidence,chord,key" in csv_text
    assert "pitch_frames" in json_text
    assert "tessitura_metrics" in json_text


def test_json_report_preserves_zero_start_timestamps() -> None:
    payload = {
        "metadata": {"sample_rate": 44100, "hop_length": 512},
        "pitch": {
            "frames": [
                {
                    "time": 0.0,
                    "f0_hz": 220.0,
                    "midi": 57.0,
                    "confidence": 0.0,
                }
            ]
        },
        "note_events": [{"start": 0.0, "end": 0.5, "label": "A3", "confidence": 0.0}],
        "chords": {"timeline": [{"start": 0.0, "end": 1.0, "label": "A:min", "confidence": 0.0}]},
        "keys": {"trajectory": [{"start": 0.0, "end": 1.0, "label": "A:min", "confidence": 0.0}]},
    }

    parsed = json.loads(generate_json_report(payload))

    assert parsed["pitch_frames"][0]["time"] == 0.0
    assert parsed["note_events"][0]["start"] == 0.0
    assert parsed["chord_timeline"][0]["start"] == 0.0
    assert parsed["key_trajectory"][0]["start"] == 0.0


def test_pdf_helpers_preserve_zero_start_and_confidence() -> None:
    assert _event_start({"start": 0.0}) == 0.0
    assert _event_start({"time": 0.0}) == 0.0
    assert _event_confidence({"confidence": 0.0}) == 0.0
    assert _event_confidence({"probability": 0.0}) == 0.0


def test_visualization_transforms_preserve_zero_start() -> None:
    piano_roll_payload = {
        "note_events": [
            {"start": 0.0, "end": 0.5, "midi": 60.0, "label": "C4", "confidence": 0.0}
        ]
    }
    piano_roll = plot_piano_roll(piano_roll_payload, backend="plotly")
    shapes = piano_roll["layout"]["shapes"]

    assert shapes
    assert shapes[0]["x0"] == 0.0

    key_payload = {
        "keys": {
            "trajectory": [
                {"start": 0.0, "label": "C:maj", "confidence": 0.0}
            ]
        }
    }
    key_plot = plot_key_stability(key_payload, backend="plotly")

    assert key_plot["data"][0]["x"][0] == 0.0
    assert key_plot["data"][0]["y"][0] == 0.0
