"""Vocal source separation using Demucs htdemucs model."""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Thread-safe singleton for the loaded model
_model_lock = threading.Lock()
_model = None
_model_name: str | None = None


@dataclass
class SeparationResult:
    vocals: np.ndarray          # float32, mono
    sample_rate: int
    model_name: str
    separation_time_s: float
    cache_hit: bool


def is_available() -> bool:
    """Return True if demucs and torch are importable."""
    try:
        import demucs  # noqa: F401
        import torch   # noqa: F401
        return True
    except ImportError:
        return False


def _load_model(model_name: str = "htdemucs"):
    """Lazily load and cache the Demucs model (thread-safe singleton)."""
    global _model, _model_name
    with _model_lock:
        if _model is None or _model_name != model_name:
            from demucs.pretrained import get_model
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("vocal_separation_model_load model=%s device=%s", model_name, device)
            _model = get_model(model_name).to(device)
            _model.eval()
            _model_name = model_name
    return _model, _model_name


def cache_key(file_path: str) -> str:
    """Compute SHA-256 hash of file contents for use as cache key."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.wav"


def load_cached_stem(cache_dir: Path, key: str) -> Optional[Tuple[np.ndarray, int]]:
    """Load a cached vocal stem. Returns (audio, sample_rate) or None."""
    path = _cache_path(cache_dir, key)
    if not path.exists():
        return None
    try:
        import soundfile as sf
        audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
        logger.info("vocal_separation_cache_hit key=%s path=%s", key[:12], path)
        return audio, sr
    except Exception as exc:
        logger.warning("vocal_separation_cache_load_failed key=%s error=%s", key[:12], exc)
        return None


_write_locks: dict[str, threading.Lock] = {}
_write_locks_lock = threading.Lock()


def _get_write_lock(key: str) -> threading.Lock:
    with _write_locks_lock:
        if key not in _write_locks:
            _write_locks[key] = threading.Lock()
        return _write_locks[key]


def save_stem_to_cache(cache_dir: Path, key: str, audio: np.ndarray, sample_rate: int) -> None:
    """Write vocal stem WAV to cache directory with per-key file locking."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, key)
    lock = _get_write_lock(key)
    with lock:
        if path.exists():
            return  # Another thread wrote it already
        try:
            import soundfile as sf
            tmp_path = path.with_suffix(".tmp.wav")
            sf.write(str(tmp_path), audio, sample_rate, subtype="PCM_16")
            tmp_path.rename(path)
            logger.info("vocal_separation_cache_write key=%s path=%s", key[:12], path)
        except Exception as exc:
            logger.warning("vocal_separation_cache_write_failed key=%s error=%s", key[:12], exc)


def separate_vocals(
    audio: np.ndarray,
    sample_rate: int,
    *,
    model_name: str = "htdemucs",
    file_path: Optional[str] = None,
    cache_dir: Optional[Path] = None,
) -> SeparationResult:
    """Separate vocals from a mixed audio signal using Demucs.

    Args:
        audio: Input audio array (float32, mono or stereo).
        sample_rate: Sample rate of audio in Hz.
        model_name: Demucs model name; default 'htdemucs'.
        file_path: If provided, used to compute cache key.
        cache_dir: If provided alongside file_path, enables disk-based stem caching.

    Returns:
        SeparationResult with vocals stem as float32 mono numpy array.
    """
    import torch

    cache_key_val: Optional[str] = None
    if file_path is not None and cache_dir is not None:
        cache_key_val = cache_key(file_path)
        cached = load_cached_stem(cache_dir, cache_key_val)
        if cached is not None:
            vocals_audio, cached_sr = cached
            return SeparationResult(
                vocals=vocals_audio,
                sample_rate=cached_sr,
                model_name=model_name,
                separation_time_s=0.0,
                cache_hit=True,
            )

    t0 = time.perf_counter()
    model, loaded_name = _load_model(model_name)
    device = next(model.parameters()).device

    # Demucs expects stereo float32 at model.samplerate
    from demucs.apply import apply_model
    import torchaudio

    audio_float = np.asarray(audio, dtype=np.float32)
    if audio_float.ndim == 1:
        audio_stereo = np.stack([audio_float, audio_float], axis=0)
    elif audio_float.shape[0] == 1:
        audio_stereo = np.concatenate([audio_float, audio_float], axis=0)
    else:
        audio_stereo = audio_float[:2]  # Take first two channels

    # Resample to model's required sample rate if needed
    model_sr = model.samplerate
    if sample_rate != model_sr:
        wav_tensor = torch.from_numpy(audio_stereo).unsqueeze(0)
        wav_tensor = torchaudio.functional.resample(wav_tensor, sample_rate, model_sr)
        audio_stereo = wav_tensor.squeeze(0).numpy()

    wav_tensor = torch.from_numpy(audio_stereo).unsqueeze(0).to(device)

    with torch.no_grad():
        sources = apply_model(model, wav_tensor, device=device, progress=False)

    # sources shape: (batch=1, stems, channels, samples)
    # Stem order in htdemucs: drums, bass, other, vocals
    stem_names = model.sources
    vocal_idx = stem_names.index("vocals")
    vocal_stereo = sources[0, vocal_idx].cpu().numpy()  # (channels, samples)
    vocals_mono = np.mean(vocal_stereo, axis=0).astype(np.float32)

    t1 = time.perf_counter()
    separation_time = t1 - t0
    logger.info(
        "vocal_separation_complete model=%s device=%s duration_samples=%d separation_time_s=%.2f",
        loaded_name, str(device), vocals_mono.shape[0], separation_time,
    )

    if cache_key_val is not None and cache_dir is not None:
        save_stem_to_cache(cache_dir, cache_key_val, vocals_mono, model_sr)

    return SeparationResult(
        vocals=vocals_mono,
        sample_rate=model_sr,
        model_name=loaded_name,
        separation_time_s=separation_time,
        cache_hit=False,
    )


def detect_audio_type(
    audio: np.ndarray,
    sample_rate: int,
    *,
    analysis_duration_s: float = 10.0,
    sub_bass_threshold: float = 0.08,
    spectral_spread_threshold: float = 0.35,
) -> str:
    """Heuristic classification of audio as 'isolated' vocals or 'mixed' track.

    Uses two spectral features computed from the first `analysis_duration_s` seconds:
    1. Sub-bass energy ratio — energy below 80 Hz relative to total. Full mixes with
       bass guitar or kick drum have significant sub-bass (~10%+). Isolated vocals
       have near-zero sub-bass.
    2. Spectral spread — normalized standard deviation of the spectral centroid over
       time. Full mixes have broader, more variable spectral distribution.

    Args:
        audio: Float32 mono audio array.
        sample_rate: Sample rate in Hz.
        analysis_duration_s: Seconds of audio to analyze (from start).
        sub_bass_threshold: Sub-bass energy fraction above which audio is classified
            as mixed. Default 0.08 (8%).
        spectral_spread_threshold: Normalized spectral spread above which audio is
            classified as mixed. Default 0.35.

    Returns:
        "isolated" if the audio appears to be a solo vocal recording, else "mixed".
    """
    segment_samples = int(analysis_duration_s * sample_rate)
    segment = np.asarray(audio, dtype=np.float32)[:segment_samples]
    if segment.size == 0:
        return "isolated"

    # Use a simple periodogram-style power spectrum
    n_fft = 2048
    hop = n_fft // 4
    n_frames = max(1, (segment.size - n_fft) // hop)
    power_frames = []
    for i in range(n_frames):
        frame = segment[i * hop: i * hop + n_fft]
        if frame.size < n_fft:
            frame = np.pad(frame, (0, n_fft - frame.size))
        windowed = frame * np.hanning(n_fft)
        spectrum = np.abs(np.fft.rfft(windowed)) ** 2
        power_frames.append(spectrum)
    power = np.mean(power_frames, axis=0)

    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    total_power = float(np.sum(power)) + 1e-12

    # Feature 1: sub-bass energy ratio (< 80 Hz)
    sub_bass_mask = freqs < 80.0
    sub_bass_ratio = float(np.sum(power[sub_bass_mask])) / total_power

    # Feature 2: spectral spread — fraction of energy outside the core vocal band
    vocal_band_mask = (freqs >= 80.0) & (freqs <= 3000.0)
    vocal_band_ratio = float(np.sum(power[vocal_band_mask])) / total_power
    non_vocal_ratio = 1.0 - vocal_band_ratio

    is_mixed = sub_bass_ratio >= sub_bass_threshold or non_vocal_ratio >= spectral_spread_threshold

    logger.debug(
        "detect_audio_type sub_bass_ratio=%.4f non_vocal_ratio=%.4f result=%s",
        sub_bass_ratio,
        non_vocal_ratio,
        "mixed" if is_mixed else "isolated",
    )
    return "mixed" if is_mixed else "isolated"
