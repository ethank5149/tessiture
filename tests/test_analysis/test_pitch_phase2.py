import numpy as np

from analysis.dsp.peak_detection import HarmonicFrame, detect_harmonics
from analysis.dsp.stft import compute_stft
from analysis.pitch.estimator import estimate_pitch_frames
from analysis.pitch.midi_converter import build_midi_frames, convert_f0_to_midi
from analysis.pitch.path_optimizer import optimize_lead_voice


def _sine_wave(freq_hz: float, sample_rate: int, duration_s: float, amplitude: float = 0.7) -> np.ndarray:
    t = np.arange(int(sample_rate * duration_s)) / float(sample_rate)
    return (amplitude * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)


def test_estimate_pitch_frames_outputs_f0_and_components() -> None:
    sample_rate = 8000
    hop_length = 128
    audio = _sine_wave(440.0, sample_rate, 0.2)

    stft = compute_stft(audio, sample_rate=sample_rate, n_fft=256, hop_length=hop_length)
    harmonic_frames = detect_harmonics(stft.spectrum, stft.frequencies, n_harmonics=3, freq_tolerance=15.0)

    frames = estimate_pitch_frames(
        stft.spectrum,
        stft.frequencies,
        harmonic_frames,
        audio=audio,
        sample_rate=sample_rate,
        hop_length=hop_length,
    )

    assert frames, "Expected pitch frames to be produced."
    first = frames[0]
    assert first.f0_hz >= 0.0, "Expected non-negative pitch estimate."
    assert {"H", "C", "S"}.issubset(first.components.keys()), "Expected salience components in output."
    assert "HPS_f0" in first.components, "Expected HPS fallback frequency in components."
    assert "analysis_diagnostics" in first.components, "Expected diagnostics payload in components."
    diagnostics = first.components["analysis_diagnostics"]
    assert diagnostics["primary_method_used"] in {
        "harmonic_candidates",
        "hps_fallback",
        "autocorrelation_fallback",
        "no_pitch_detected",
    }
    assert diagnostics["attempted_methods"] == [
        "harmonic_candidates",
        "hps_peak_ratio_gate",
        "autocorrelation",
    ]
    assert "strategy_path" in diagnostics
    assert "fallback_reason" in diagnostics


def test_estimate_pitch_frames_emits_fallback_reason_when_no_viable_pitch_methods() -> None:
    spectrum = np.zeros((8, 1), dtype=np.float32)
    frequencies = np.linspace(0.0, 700.0, 8, dtype=np.float32)
    harmonic_frames = [HarmonicFrame(time_index=0, candidates=[])]
    audio = np.zeros(400, dtype=np.float32)

    frames = estimate_pitch_frames(
        spectrum,
        frequencies,
        harmonic_frames,
        audio=audio,
        sample_rate=8000,
        hop_length=128,
    )

    assert len(frames) == 1
    diagnostics = frames[0].components["analysis_diagnostics"]
    assert diagnostics["primary_method_used"] == "no_pitch_detected"
    assert diagnostics["fallback_reason"] == "no_harmonic_candidates_and_no_viable_fallback"


def test_optimize_lead_voice_returns_path_with_matching_length() -> None:
    candidates = [
        type("PF", (), {"f0_hz": 440.0, "salience": 0.9}),
        type("PF", (), {"f0_hz": 445.0, "salience": 0.85}),
        type("PF", (), {"f0_hz": 442.0, "salience": 0.88}),
    ]

    path = optimize_lead_voice(candidates)

    assert path.f0_hz.size == len(candidates), "Expected path length to match number of frames."
    assert path.salience.size == len(candidates), "Expected salience length to match number of frames."
    assert path.path_indices.size == len(candidates), "Expected path indices to match number of frames."


def test_optimize_lead_voice_prefers_higher_salience_with_penalty() -> None:
    primary = [
        type("PF", (), {"f0_hz": 440.0, "salience": 0.6}),
        type("PF", (), {"f0_hz": 880.0, "salience": 0.6}),
    ]
    alt = [
        [type("PF", (), {"f0_hz": 445.0, "salience": 0.55})],
        [type("PF", (), {"f0_hz": 450.0, "salience": 0.55})],
    ]

    path = optimize_lead_voice(primary, alt_candidates=alt, jump_penalty=1.5)

    assert np.all(path.f0_hz > 0.0), "Expected optimized path to use positive frequencies."


def test_convert_f0_to_midi_with_uncertainty_and_calibration() -> None:
    f0_hz = np.array([440.0, 0.0, 880.0], dtype=np.float32)
    sigma_f = np.array([1.5, 0.0, 2.0], dtype=np.float32)

    def calibrate(freq: float) -> tuple[float, float]:
        return (1.0, 0.5)

    midi_vals, midi_sigma = convert_f0_to_midi(f0_hz, sigma_f=sigma_f, calibrate=calibrate)

    assert midi_vals.shape == f0_hz.shape, "Expected midi values to mirror input shape."
    assert midi_sigma.shape == f0_hz.shape, "Expected midi uncertainty to mirror input shape."
    assert midi_sigma[0] > 0.0, "Expected non-zero uncertainty after calibration."
    assert midi_vals[1] == 0.0 and midi_sigma[1] == 0.0, "Expected zeros for non-positive frequencies."


def test_build_midi_frames_includes_uncertainty_and_cents() -> None:
    f0_hz = np.array([440.0, 466.16], dtype=np.float32)
    sigma_f = np.array([1.0, 1.0], dtype=np.float32)

    frames = build_midi_frames(f0_hz, sigma_f=sigma_f)

    assert len(frames) == f0_hz.size, "Expected one MIDI frame per input frequency."
    assert frames[0].midi_uncertainty > 0.0, "Expected midi uncertainty propagated to frames."
    assert abs(frames[0].cents_deviation) < 1e-3, "Expected near-zero cents deviation for 440 Hz (A4)."
