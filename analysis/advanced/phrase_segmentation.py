"""Phrase segmentation via energy-based boundary detection and continuity analysis."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class PhraseBoundary:
    """Boundary between phrases with timestamp and simple confidence."""
    time_s: float
    confidence: float
    index: int
    kind: str


@dataclass(frozen=True)
class PhraseSegmentationResult:
    """Segmentation output with boundaries and energy envelope context."""
    boundaries: List[PhraseBoundary]
    energy: np.ndarray
    times_s: np.ndarray
    threshold_db: float


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    kernel = np.ones(int(window), dtype=float)
    kernel /= float(np.sum(kernel))
    return np.convolve(values, kernel, mode="same")


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    if audio.ndim != 2:
        raise ValueError("audio must be 1D or 2D array")
    if audio.shape[0] <= 8:
        return np.mean(audio, axis=0)
    return np.mean(audio, axis=1)


def _mask_to_segments(mask: np.ndarray) -> List[Tuple[int, int]]:
    segments: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for idx, active in enumerate(mask):
        if active and start is None:
            start = idx
        elif not active and start is not None:
            segments.append((start, idx - 1))
            start = None
    if start is not None:
        segments.append((start, int(mask.size - 1)))
    return segments


def _median_window(values: np.ndarray, start: int, end: int) -> float:
    start = max(0, int(start))
    end = min(int(values.size), int(end))
    if start >= end:
        return 0.0
    return float(np.median(values[start:end]))


def _gap_confidence(gap_s: float, continuity_ratio: float, min_pause_s: float) -> float:
    safe_pause = max(float(min_pause_s), np.finfo(float).eps)
    duration_score = min(1.0, float(gap_s) / (safe_pause * 2.0))
    discontinuity = 1.0 - float(continuity_ratio)
    confidence = 0.6 * duration_score + 0.4 * discontinuity
    return float(np.clip(confidence, 0.0, 1.0))


def compute_energy_envelope(
    audio: Sequence[float],
    sample_rate: int,
    *,
    frame_length: int = 2048,
    hop_length: int = 512,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute a frame-level RMS energy envelope from audio."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    values = np.asarray(audio, dtype=float)
    if values.size == 0:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=float)
    values = _to_mono(values)
    frame_length = int(frame_length)
    hop_length = int(hop_length)
    if frame_length <= 0 or hop_length <= 0:
        raise ValueError("frame_length and hop_length must be positive")
    if values.size <= frame_length:
        n_frames = 1
    else:
        n_frames = 1 + int(np.ceil((values.size - frame_length) / float(hop_length)))

    energies = np.zeros(n_frames, dtype=float)
    for idx in range(n_frames):
        start = idx * hop_length
        end = min(start + frame_length, int(values.size))
        frame = values[start:end]
        if frame.size < frame_length:
            frame = np.pad(frame, (0, frame_length - frame.size))
        energies[idx] = float(np.sqrt(np.mean(frame * frame)))

    times = np.arange(n_frames, dtype=float) * (float(hop_length) / float(sample_rate))
    return energies, times


def segment_phrases_from_energy(
    energy: Sequence[float],
    sample_rate: int,
    hop_length: int,
    *,
    times_s: Optional[Sequence[float]] = None,
    energy_floor_db: float = -45.0,
    energy_smooth_s: float = 0.05,
    min_pause_s: float = 0.15,
    min_phrase_s: float = 0.25,
    continuity_window_s: float = 0.12,
    continuity_min_ratio: float = 0.65,
) -> PhraseSegmentationResult:
    """Segment phrases from a precomputed energy envelope.

    Args:
        energy: Frame-level energy values (RMS or similar).
        sample_rate: Audio sample rate in Hz.
        hop_length: Hop length in samples between energy frames.
        times_s: Optional explicit times for each energy frame.
        energy_floor_db: Relative dB threshold for silence detection.
        energy_smooth_s: Smoothing window (seconds) for the energy envelope.
        min_pause_s: Minimum silence duration to declare a boundary.
        min_phrase_s: Minimum phrase duration to keep a boundary.
        continuity_window_s: Window around gaps to measure continuity.
        continuity_min_ratio: Energy ratio above which gaps are treated as continuous.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if hop_length <= 0:
        raise ValueError("hop_length must be positive")

    energy_values = np.asarray(energy, dtype=float)
    if energy_values.ndim != 1:
        raise ValueError("energy must be a 1D array")
    if energy_values.size == 0:
        return PhraseSegmentationResult([], energy_values, np.zeros(0, dtype=float), float(energy_floor_db))

    if times_s is None:
        frame_duration = float(hop_length) / float(sample_rate)
        times = np.arange(energy_values.size, dtype=float) * frame_duration
    else:
        times = np.asarray(times_s, dtype=float)
        if times.shape[0] != energy_values.shape[0]:
            raise ValueError("times_s length must match energy length")
        frame_duration = float(hop_length) / float(sample_rate)

    smooth_frames = max(1, int(round(float(energy_smooth_s) / frame_duration)))
    smooth_energy = _moving_average(energy_values, smooth_frames)
    eps = np.finfo(float).eps
    energy_db = 20.0 * np.log10(np.maximum(smooth_energy, eps))
    max_db = float(np.max(energy_db))
    if np.isfinite(max_db):
        energy_db = energy_db - max_db
    else:
        energy_db = np.full_like(energy_db, -120.0)

    voiced_mask = energy_db >= float(energy_floor_db)
    segments = _mask_to_segments(voiced_mask)
    if not segments:
        return PhraseSegmentationResult([], smooth_energy, times, float(energy_floor_db))

    frame_rate = 1.0 / frame_duration
    continuity_frames = max(1, int(round(float(continuity_window_s) * frame_rate)))
    boundaries: List[PhraseBoundary] = []

    for idx in range(len(segments) - 1):
        prev_start, prev_end = segments[idx]
        next_start, next_end = segments[idx + 1]
        gap_start = prev_end + 1
        gap_end = next_start - 1
        if gap_end < gap_start:
            continue
        gap_frames = gap_end - gap_start + 1
        gap_duration = gap_frames * frame_duration
        if gap_duration < float(min_pause_s):
            continue

        prev_duration = (prev_end - prev_start + 1) * frame_duration
        next_duration = (next_end - next_start + 1) * frame_duration
        if prev_duration < float(min_phrase_s) or next_duration < float(min_phrase_s):
            continue

        pre_energy = _median_window(smooth_energy, prev_end - continuity_frames + 1, prev_end + 1)
        post_energy = _median_window(smooth_energy, next_start, next_start + continuity_frames)
        denom = max(pre_energy, post_energy, eps)
        continuity_ratio = min(pre_energy, post_energy) / denom
        if continuity_ratio >= float(continuity_min_ratio) and gap_duration < float(min_pause_s) * 2.0:
            continue

        gap_confidence = _gap_confidence(gap_duration, continuity_ratio, min_pause_s)
        # Interpolate boundary time to midpoint between last voiced and first silent frame
        # This halves the worst-case quantization error vs. using frame center directly
        if prev_end + 1 < len(times):
            end_boundary_time = 0.5 * (float(times[prev_end]) + float(times[prev_end + 1]))
        else:
            end_boundary_time = float(times[prev_end])
        if next_start > 0:
            start_boundary_time = 0.5 * (float(times[next_start - 1]) + float(times[next_start]))
        else:
            start_boundary_time = float(times[next_start])
        boundaries.append(
            PhraseBoundary(
                time_s=end_boundary_time,
                confidence=gap_confidence,
                index=int(prev_end),
                kind="end",
            )
        )
        boundaries.append(
            PhraseBoundary(
                time_s=start_boundary_time,
                confidence=gap_confidence,
                index=int(next_start),
                kind="start",
            )
        )

    first_start = segments[0][0]
    last_end = segments[-1][1]
    boundaries.append(
        PhraseBoundary(
            time_s=float(times[first_start]),
            confidence=1.0,
            index=int(first_start),
            kind="start",
        )
    )
    boundaries.append(
        PhraseBoundary(
            time_s=float(times[last_end]),
            confidence=1.0,
            index=int(last_end),
            kind="end",
        )
    )

    boundaries.sort(key=lambda b: (b.index, 0 if b.kind == "start" else 1))
    return PhraseSegmentationResult(boundaries, smooth_energy, times, float(energy_floor_db))


def segment_phrases_from_audio(
    audio: Sequence[float],
    sample_rate: int,
    *,
    frame_length: int = 2048,
    hop_length: int = 512,
    energy_floor_db: float = -45.0,
    energy_smooth_s: float = 0.05,
    min_pause_s: float = 0.15,
    min_phrase_s: float = 0.25,
    continuity_window_s: float = 0.12,
    continuity_min_ratio: float = 0.65,
) -> PhraseSegmentationResult:
    """Segment phrases directly from audio samples."""
    energy, times = compute_energy_envelope(
        audio,
        sample_rate,
        frame_length=frame_length,
        hop_length=hop_length,
    )
    return segment_phrases_from_energy(
        energy,
        sample_rate,
        hop_length,
        times_s=times,
        energy_floor_db=energy_floor_db,
        energy_smooth_s=energy_smooth_s,
        min_pause_s=min_pause_s,
        min_phrase_s=min_phrase_s,
        continuity_window_s=continuity_window_s,
        continuity_min_ratio=continuity_min_ratio,
    )


__all__ = [
    "PhraseBoundary",
    "PhraseSegmentationResult",
    "compute_energy_envelope",
    "segment_phrases_from_audio",
    "segment_phrases_from_energy",
]
