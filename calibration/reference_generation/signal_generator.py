"""Synthetic signal generation for calibration reference datasets."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np


def _dbfs_to_linear(dbfs: float) -> float:
    """Convert dBFS amplitude to linear scale."""

    return float(10.0 ** (dbfs / 20.0))


def _cents_to_ratio(cents: float) -> float:
    """Convert cents offset to frequency ratio."""

    return float(2.0 ** (cents / 1200.0))


def _note_count_from_params(params: Dict[str, Any]) -> int:
    """Extract and clamp note count from params."""

    raw = int(round(float(params.get("note_count", 1.0))))
    return int(np.clip(raw, 1, 4))


def generate_synthetic_signal(
    params: Dict[str, Any],
    sample_rate: int = 44100,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Generate a synthetic harmonic signal with optional vibrato and detuning.

    Args:
        params: Parameter dictionary with keys such as f0_hz, detune_cents,
            amplitude_dbfs, harmonic_ratio, note_count, duration_s, snr_db,
            vibrato_depth_cents, and vibrato_rate_hz.
        sample_rate: Sample rate for the generated signal.
        rng: Optional random generator for reproducible noise injection. If
            None, a new default RNG is created each call.

    Returns:
        Tuple of (audio array, metadata dict).
    """

    duration_s = float(params.get("duration_s", 1.0))
    if duration_s <= 0:
        raise ValueError("duration_s must be positive.")

    f0_hz = float(params.get("f0_hz", 440.0))
    detune_cents = float(params.get("detune_cents", 0.0))
    amplitude_dbfs = float(params.get("amplitude_dbfs", -12.0))
    harmonic_ratio = float(params.get("harmonic_ratio", 0.5))
    snr_db = float(params.get("snr_db", 40.0))
    vibrato_depth_cents = float(params.get("vibrato_depth_cents", 0.0))
    vibrato_rate_hz = float(params.get("vibrato_rate_hz", 5.0))

    note_count = _note_count_from_params(params)

    n_samples = int(round(duration_s * sample_rate))
    t = np.arange(n_samples, dtype=float) / float(sample_rate)

    if note_count == 1:
        cents_offsets = np.array([detune_cents], dtype=float)
    else:
        cents_offsets = np.linspace(-detune_cents, detune_cents, note_count, dtype=float)

    base_frequencies = f0_hz * np.array([_cents_to_ratio(c) for c in cents_offsets])

    base_amp = _dbfs_to_linear(amplitude_dbfs)
    harmonic_ratio = float(np.clip(harmonic_ratio, 0.0, 1.0))

    signal = np.zeros_like(t)
    nyquist = sample_rate / 2.0

    for freq in base_frequencies:
        if freq <= 0:
            continue
        max_harmonics = int(min(20, np.floor(nyquist / freq)))
        if max_harmonics <= 0:
            continue

        if vibrato_depth_cents != 0.0 and vibrato_rate_hz > 0.0:
            vibrato = _cents_to_ratio(vibrato_depth_cents * np.sin(2.0 * np.pi * vibrato_rate_hz * t))
        else:
            vibrato = 1.0

        inst_freq = freq * vibrato
        phase = 2.0 * np.pi * np.cumsum(inst_freq) / float(sample_rate)

        for harmonic in range(1, max_harmonics + 1):
            amp = base_amp * (harmonic_ratio ** (harmonic - 1))
            signal += amp * np.sin(harmonic * phase)

    if signal.size > 0:
        peak = np.max(np.abs(signal))
        if peak > 0:
            signal = signal / peak

    if snr_db is not None and np.isfinite(snr_db):
        signal_power = float(np.mean(signal ** 2)) if signal.size > 0 else 0.0
        if signal_power > 0:
            noise_power = signal_power / float(10.0 ** (snr_db / 10.0))
            _rng = rng if rng is not None else np.random.default_rng()
            noise = _rng.normal(scale=np.sqrt(noise_power), size=signal.shape)
            signal = signal + noise

    midi_numbers = 69.0 + 12.0 * np.log2(base_frequencies / 440.0)

    metadata: Dict[str, Any] = {
        "note_count": note_count,
        "note_frequencies_hz": base_frequencies.tolist(),
        "note_midi": midi_numbers.tolist(),
        "sample_rate": sample_rate,
        "duration_s": duration_s,
        "f0_hz": f0_hz,
        "detune_cents": detune_cents,
        "amplitude_dbfs": amplitude_dbfs,
        "harmonic_ratio": harmonic_ratio,
        "snr_db": snr_db,
        "vibrato_depth_cents": vibrato_depth_cents,
        "vibrato_rate_hz": vibrato_rate_hz,
    }

    return signal.astype(np.float32), metadata
