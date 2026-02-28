from __future__ import annotations

import logging
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from analysis.advanced.formants import estimate_formants_from_audio
from analysis.advanced.phrase_segmentation import segment_phrases_from_audio
from analysis.advanced.vibrato import detect_vibrato
from analysis.chords.detector import detect_chord
from analysis.chords.key_detector import detect_key
from analysis.dsp.peak_detection import detect_harmonics
from analysis.dsp.preprocessing import preprocess_audio
from analysis.dsp.stft import compute_stft
from analysis.pitch.estimator import estimate_pitch_frames
from analysis.pitch.midi_converter import convert_f0_to_midi
from analysis.pitch.path_optimizer import optimize_lead_voice
from analysis.tessitura.analyzer import analyze_tessitura
from api import job_manager
from calibration.monte_carlo.uncertainty_analyzer import summarize_uncertainty
from reporting import generate_csv_report, generate_json_report, generate_pdf_report

router = APIRouter()
logger = logging.getLogger(__name__)

# Upload and output configuration
UPLOAD_DIR = Path(os.getenv("TESSITURE_UPLOAD_DIR", "/tmp/tessiture_uploads"))
OUTPUT_DIR = Path(os.getenv("TESSITURE_OUTPUT_DIR", "/tmp/tessiture_outputs"))
EXAMPLES_DIR = Path(
    os.getenv(
        "TESSITURE_EXAMPLES_DIR",
        str(Path(__file__).resolve().parents[1] / "examples" / "tracks"),
    )
)
DEFAULT_UPLOAD_EXTENSIONS = ".wav,.mp3,.flac,.m4a,.opus"
DEFAULT_UPLOAD_MIME_TYPES = (
    "audio/wav,audio/x-wav,audio/mpeg,audio/flac,audio/x-flac,audio/mp4,"
    "audio/opus,audio/x-opus,audio/ogg,application/ogg"
)
ALLOWED_EXTENSIONS: Set[str] = {
    (ext if ext.startswith(".") else f".{ext}")
    for ext in (
        part.strip().lower()
        for part in os.getenv("TESSITURE_UPLOAD_EXTENSIONS", DEFAULT_UPLOAD_EXTENSIONS).split(",")
    )
    if ext
}
ALLOWED_MIME_TYPES: Set[str] = {
    mime
    for mime in (
        part.strip().lower()
        for part in os.getenv("TESSITURE_UPLOAD_MIME_TYPES", DEFAULT_UPLOAD_MIME_TYPES).split(",")
    )
    if mime
}
MAX_UPLOAD_BYTES = int(os.getenv("TESSITURE_UPLOAD_MAX_BYTES", str(25 * 1024 * 1024)))

# Analysis defaults
TARGET_SAMPLE_RATE = int(os.getenv("TESSITURE_TARGET_SAMPLE_RATE", "44100"))
STFT_NFFT = int(os.getenv("TESSITURE_STFT_NFFT", "4096"))
STFT_HOP = int(os.getenv("TESSITURE_STFT_HOP", "512"))

# Rate limiting placeholder (token bucket per client IP).
RATE_LIMIT_CAPACITY = int(os.getenv("TESSITURE_RATE_LIMIT_CAPACITY", "10"))
RATE_LIMIT_REFILL_PER_SEC = float(os.getenv("TESSITURE_RATE_LIMIT_REFILL_PER_SEC", "0.5"))
_RATE_LIMIT_BUCKETS: Dict[str, Dict[str, float]] = {}

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

EXAMPLE_CONTENT_TYPE_OVERRIDES: Dict[str, str] = {
    ".opus": "audio/opus",
    ".m4a": "audio/mp4",
}


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _build_example_payload(example: Mapping[str, Any], file_path: Path) -> Dict[str, Any]:
    return {
        "id": str(example.get("id") or ""),
        "display_name": str(example.get("display_name") or file_path.stem),
        "filename": file_path.name,
        "content_type": str(example.get("content_type") or "audio/*"),
        "size_bytes": int(file_path.stat().st_size),
    }


def _slugify_example_id(file_path: Path) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", file_path.stem.lower()).strip("-")
    return base or "example"


def _guess_example_content_type(file_path: Path) -> str:
    extension = file_path.suffix.lower()
    if extension in EXAMPLE_CONTENT_TYPE_OVERRIDES:
        return EXAMPLE_CONTENT_TYPE_OVERRIDES[extension]
    guessed, _ = mimetypes.guess_type(file_path.name)
    return guessed or "audio/*"


def _discover_example_tracks() -> List[tuple[Dict[str, Any], Path]]:
    discovered: List[tuple[Dict[str, Any], Path]] = []
    used_ids: Set[str] = set()
    examples_root = EXAMPLES_DIR.resolve()

    if not examples_root.exists():
        logger.warning("example_gallery.examples_root_missing examples_root=%s", examples_root)
        return discovered

    logger.info("example_gallery.discovery_start examples_root=%s", examples_root)

    for candidate in sorted(examples_root.iterdir(), key=lambda path: path.name.lower()):
        resolved = candidate.resolve()
        if not candidate.is_file():
            continue

        try:
            resolved.relative_to(examples_root)
        except ValueError:
            logger.warning(
                "example_gallery.skipped_outside_root filename=%s candidate=%s root=%s",
                candidate.name,
                resolved,
                examples_root,
            )
            continue

        extension = candidate.suffix.lower()
        if extension and extension not in ALLOWED_EXTENSIONS:
            logger.info(
                "example_gallery.skipped_unsupported_extension filename=%s extension=%s",
                candidate.name,
                extension,
            )
            continue

        base_id = _slugify_example_id(candidate)
        example_id = base_id
        dedupe_index = 2
        while example_id in used_ids:
            example_id = f"{base_id}-{dedupe_index}"
            dedupe_index += 1
        used_ids.add(example_id)

        example_payload = {
            "id": example_id,
            "display_name": candidate.stem,
            "filename": candidate.name,
            "content_type": _guess_example_content_type(candidate),
        }

        logger.info(
            "example_gallery.inspect_candidate id=%s candidate=%s exists=%s",
            example_id,
            resolved,
            resolved.is_file(),
        )
        discovered.append((_build_example_payload(example_payload, resolved), resolved))

    logger.info("example_gallery.discovery_complete available_examples=%d", len(discovered))
    return discovered


def _list_available_example_tracks() -> List[Dict[str, Any]]:
    return [example for example, _ in _discover_example_tracks()]


def _resolve_example_track(example_id: str) -> tuple[Dict[str, Any], Path]:
    normalized_id = (example_id or "").strip()
    if not normalized_id:
        raise HTTPException(status_code=400, detail="Example ID is required.")

    logger.info("example_gallery.resolve_start requested_id=%s", normalized_id)

    discovered = _discover_example_tracks()
    discovered_ids = [example.get("id", "") for example, _ in discovered]

    for example, file_path in discovered:
        configured_id = str(example.get("id") or "").strip()
        if configured_id != normalized_id:
            continue

        logger.info(
            "example_gallery.resolve_success requested_id=%s filename=%s",
            normalized_id,
            example.get("filename"),
        )
        return example, file_path

    logger.warning(
        "example_gallery.resolve_not_found requested_id=%s discovered_ids=%s",
        normalized_id,
        discovered_ids,
    )
    raise HTTPException(status_code=404, detail="Example track not found.")


async def _save_upload(upload: UploadFile) -> Path:
    _ensure_upload_dir()
    suffix = _validate_upload(upload)
    file_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    total_bytes = 0
    try:
        with file_path.open("wb") as buffer:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload exceeds maximum size.")
                buffer.write(chunk)
    except HTTPException:
        if file_path.exists():
            file_path.unlink()
        raise
    finally:
        await upload.close()
    return file_path


def _validate_upload(upload: UploadFile) -> str:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Audio filename is required.")
    suffix = Path(upload.filename).suffix.lower()
    if not suffix or suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported audio file extension.")
    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio MIME type.")
    return suffix


def _rate_limit_check(request: Request) -> None:
    if RATE_LIMIT_CAPACITY <= 0 or RATE_LIMIT_REFILL_PER_SEC <= 0:
        return
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _RATE_LIMIT_BUCKETS.get(client_ip)
    if bucket is None:
        _RATE_LIMIT_BUCKETS[client_ip] = {"tokens": RATE_LIMIT_CAPACITY - 1, "last": now}
        return
    tokens = min(
        RATE_LIMIT_CAPACITY,
        bucket["tokens"] + (now - bucket["last"]) * RATE_LIMIT_REFILL_PER_SEC,
    )
    if tokens < 1:
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    bucket["tokens"] = tokens - 1
    bucket["last"] = now


def _serialize_status(job: job_manager.JobStatus) -> Dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "result_path": job.result_path,
        "error": job.error,
    }


def _extract_result_path(result: Mapping[str, Any], fmt: str) -> Optional[str]:
    files = result.get("files") if isinstance(result, Mapping) else None
    if isinstance(files, Mapping) and files.get(fmt):
        return str(files.get(fmt))
    key = f"{fmt}_path"
    if isinstance(result, Mapping) and result.get(key):
        return str(result.get(key))
    if isinstance(result, Mapping) and result.get("result_path"):
        return str(result.get("result_path"))
    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _midi_to_note_name(midi_value: float) -> str:
    rounded = int(round(float(midi_value)))
    note_index = rounded % 12
    octave = rounded // 12 - 1
    return f"{NOTE_NAMES[note_index]}{octave}"


def _build_pitch_payload(
    f0_hz: np.ndarray,
    salience: np.ndarray,
    midi_values: np.ndarray,
    midi_sigma: np.ndarray,
    sample_rate: int,
    hop_length: int,
) -> List[Dict[str, Any]]:
    frames: List[Dict[str, Any]] = []
    if f0_hz.size == 0:
        return frames

    sal = np.asarray(salience, dtype=float)
    if sal.size != f0_hz.size:
        sal = np.zeros_like(f0_hz, dtype=float)
    sal_min = float(np.min(sal)) if sal.size else 0.0
    sal_max = float(np.max(sal)) if sal.size else 0.0
    sal_den = max(sal_max - sal_min, 1e-9)

    for index in range(int(f0_hz.size)):
        f0 = float(f0_hz[index])
        midi = float(midi_values[index]) if index < midi_values.size else 0.0
        sigma = float(midi_sigma[index]) if index < midi_sigma.size else 0.0
        confidence = float(np.clip((sal[index] - sal_min) / sal_den, 0.0, 1.0))
        if f0 <= 0.0 or midi <= 0.0:
            frames.append(
                {
                    "index": index,
                    "time": float(index * hop_length / max(sample_rate, 1)),
                    "f0_hz": None,
                    "midi": None,
                    "note": None,
                    "cents": None,
                    "confidence": 0.0,
                    "uncertainty": None,
                }
            )
            continue
        cents = float((midi - round(midi)) * 100.0)
        frames.append(
            {
                "index": index,
                "time": float(index * hop_length / max(sample_rate, 1)),
                "f0_hz": f0,
                "midi": midi,
                "note": _midi_to_note_name(midi),
                "cents": cents,
                "confidence": confidence,
                "uncertainty": sigma,
            }
        )
    return frames


def _build_note_events(frames: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    start_idx: Optional[int] = None
    active_values: List[float] = []
    active_confidence: List[float] = []

    def _close_event(end_idx: int) -> None:
        nonlocal start_idx, active_values, active_confidence
        if start_idx is None or not active_values:
            start_idx = None
            active_values = []
            active_confidence = []
            return
        start_time = _safe_float(frames[start_idx].get("time")) or 0.0
        end_time = _safe_float(frames[end_idx].get("time")) or start_time
        midi_mean = float(np.mean(np.asarray(active_values, dtype=float)))
        confidence = (
            float(np.mean(np.asarray(active_confidence, dtype=float))) if active_confidence else 0.0
        )
        events.append(
            {
                "start": float(start_time),
                "end": float(end_time),
                "duration": float(max(end_time - start_time, 0.0)),
                "pitch": midi_mean,
                "midi": midi_mean,
                "note": _midi_to_note_name(midi_mean),
                "confidence": confidence,
            }
        )
        start_idx = None
        active_values = []
        active_confidence = []

    for idx, frame in enumerate(frames):
        midi_value = _safe_float(frame.get("midi"))
        if midi_value is None:
            if start_idx is not None:
                _close_event(idx - 1)
            continue
        if start_idx is None:
            start_idx = idx
        active_values.append(midi_value)
        active_confidence.append(_safe_float(frame.get("confidence")) or 0.0)

    if start_idx is not None:
        _close_event(len(frames) - 1)

    return events


def _build_chord_timeline(note_events: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    for event in note_events:
        midi_value = _safe_float(event.get("midi"))
        if midi_value is None:
            continue
        detected = detect_chord([midi_value], input_unit="midi", max_notes=4, top_k=3)
        label = detected.best_chord or str(event.get("note") or "Unknown")
        probability = float(detected.probabilities.get(label, 0.0)) if detected.probabilities else 0.0
        timeline.append(
            {
                "start": _safe_float(event.get("start")) or 0.0,
                "end": _safe_float(event.get("end")),
                "label": label,
                "confidence": probability,
            }
        )
    return timeline


def _serialize_tessitura_payload(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    metrics = getattr(payload, "metrics", None)
    pdf = getattr(payload, "pdf", None)
    if metrics is None:
        return {}

    strain_zones = []
    for zone in getattr(metrics, "strain_zones", ()):
        strain_zones.append(
            {
                "label": getattr(zone, "label", None),
                "low": _safe_float(getattr(zone, "low", None)),
                "high": _safe_float(getattr(zone, "high", None)),
                "reason": getattr(zone, "reason", None),
            }
        )

    serialized: Dict[str, Any] = {
        "metrics": {
            "count": int(getattr(metrics, "count", 0)),
            "weight_sum": _safe_float(getattr(metrics, "weight_sum", None)),
            "range_min": _safe_float(getattr(metrics, "range_min", None)),
            "range_max": _safe_float(getattr(metrics, "range_max", None)),
            "tessitura_band": list(getattr(metrics, "tessitura_band", ())),
            "comfort_band": list(getattr(metrics, "comfort_band", ())),
            "comfort_center": _safe_float(getattr(metrics, "comfort_center", None)),
            "variance": _safe_float(getattr(metrics, "variance", None)),
            "std_dev": _safe_float(getattr(metrics, "std_dev", None)),
            "mean_variance": _safe_float(getattr(metrics, "mean_variance", None)),
            "strain_zones": strain_zones,
        }
    }

    if pdf is not None:
        serialized["pdf"] = {
            "bin_edges": np.asarray(getattr(pdf, "bin_edges", []), dtype=float).tolist(),
            "density": np.asarray(getattr(pdf, "density", []), dtype=float).tolist(),
            "bin_centers": np.asarray(getattr(pdf, "bin_centers", []), dtype=float).tolist(),
            "bin_size": _safe_float(getattr(pdf, "bin_size", None)),
            "total_weight": _safe_float(getattr(pdf, "total_weight", None)),
        }
    return serialized


def _summarize_formants(track: Any) -> Dict[str, Any]:
    if track is None:
        return {}
    f1 = np.asarray(getattr(track, "f1_hz", []), dtype=float)
    f2 = np.asarray(getattr(track, "f2_hz", []), dtype=float)
    f3 = np.asarray(getattr(track, "f3_hz", []), dtype=float)
    return {
        "n_frames": int(f1.size),
        "f1_hz_mean": _safe_float(np.mean(f1) if f1.size else None),
        "f2_hz_mean": _safe_float(np.mean(f2) if f2.size else None),
        "f3_hz_mean": _safe_float(np.mean(f3) if f3.size else None),
    }


def _summarize_phrases(phrase_result: Any) -> Dict[str, Any]:
    boundaries = []
    for boundary in getattr(phrase_result, "boundaries", []):
        boundaries.append(
            {
                "time_s": _safe_float(getattr(boundary, "time_s", None)),
                "confidence": _safe_float(getattr(boundary, "confidence", None)),
                "index": int(getattr(boundary, "index", 0)),
                "kind": getattr(boundary, "kind", None),
            }
        )
    return {
        "threshold_db": _safe_float(getattr(phrase_result, "threshold_db", None)),
        "boundary_count": len(boundaries),
        "boundaries": boundaries,
    }


def _build_summary(result: Mapping[str, Any], duration_seconds: float) -> Dict[str, Any]:
    pitch_frames = result.get("pitch", {}).get("frames", []) if isinstance(result, Mapping) else []
    voiced_f0 = [float(item["f0_hz"]) for item in pitch_frames if _safe_float(item.get("f0_hz"))]
    confidences = [
        float(item["confidence"])
        for item in pitch_frames
        if _safe_float(item.get("confidence")) is not None
    ]
    mean_confidence = float(np.mean(confidences)) if confidences else 0.0

    tessitura_metrics = result.get("tessitura", {}).get("metrics", {}) if isinstance(result, Mapping) else {}
    tessitura_band = tessitura_metrics.get("tessitura_band") if isinstance(tessitura_metrics, Mapping) else None
    key_trajectory = result.get("keys", {}).get("trajectory", []) if isinstance(result, Mapping) else []
    key_confidence = 0.0
    if isinstance(key_trajectory, Sequence) and key_trajectory:
        key_confidence = _safe_float(key_trajectory[0].get("confidence")) or 0.0

    return {
        "duration_seconds": float(duration_seconds),
        "f0_min": float(np.min(voiced_f0)) if voiced_f0 else None,
        "f0_max": float(np.max(voiced_f0)) if voiced_f0 else None,
        "tessitura_range": tessitura_band,
        "overall_confidence": float(np.clip((mean_confidence + key_confidence) / 2.0, 0.0, 1.0)),
        "confidence": mean_confidence,
    }


def _decode_audio_file(file_path: str) -> tuple[np.ndarray, int]:
    try:
        import librosa
    except Exception as exc:  # pragma: no cover - dependency/environment guard
        raise RuntimeError("librosa is required for audio decoding.") from exc

    suffix = Path(file_path).suffix.lower()
    try:
        audio, sample_rate = librosa.load(file_path, sr=None, mono=False)
    except Exception as exc:
        if suffix == ".opus":
            raise RuntimeError(
                "Failed to decode Opus audio. Ensure FFmpeg or libsndfile with Opus support is "
                "installed and the input is a valid Opus stream."
            ) from exc
        raise RuntimeError(f"Failed to decode audio file '{Path(file_path).name}'.") from exc

    return np.asarray(audio), int(sample_rate)


def _run_analysis_pipeline(file_path: str, metadata: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    _ensure_output_dir()
    warnings: List[str] = []

    audio, sample_rate = _decode_audio_file(file_path)
    preprocessed = preprocess_audio(
        audio,
        sample_rate=int(sample_rate),
        target_sr=TARGET_SAMPLE_RATE,
        mono=True,
        normalize=True,
    )
    mono_audio = preprocessed.audio
    sample_rate = int(preprocessed.sample_rate)

    stft_result = compute_stft(
        mono_audio,
        sample_rate=sample_rate,
        n_fft=STFT_NFFT,
        hop_length=STFT_HOP,
    )
    harmonic_frames = detect_harmonics(
        stft_result.spectrum,
        stft_result.frequencies,
        n_harmonics=4,
        freq_tolerance=8.0,
        min_db=-60.0,
        max_candidates=6,
    )
    pitch_candidates = estimate_pitch_frames(
        stft_result.spectrum,
        stft_result.frequencies,
        harmonic_frames,
        audio=mono_audio,
        sample_rate=sample_rate,
        hop_length=STFT_HOP,
    )
    optimized = optimize_lead_voice(pitch_candidates)

    if optimized.f0_hz.size:
        sigma_f = np.interp(
            np.clip(optimized.f0_hz, stft_result.frequencies[0], stft_result.frequencies[-1]),
            stft_result.frequencies,
            stft_result.sigma_f,
            left=float(stft_result.sigma_f[0]),
            right=float(stft_result.sigma_f[-1]),
        )
    else:
        sigma_f = np.asarray([], dtype=float)

    midi_values, midi_sigma = convert_f0_to_midi(optimized.f0_hz, sigma_f=sigma_f)
    pitch_frames = _build_pitch_payload(
        optimized.f0_hz,
        optimized.salience,
        midi_values,
        midi_sigma,
        sample_rate=sample_rate,
        hop_length=STFT_HOP,
    )
    note_events = _build_note_events(pitch_frames)
    chord_timeline = _build_chord_timeline(note_events)

    voiced_midi = [float(frame["midi"]) for frame in pitch_frames if _safe_float(frame.get("midi"))]
    voiced_f0 = [float(frame["f0_hz"]) for frame in pitch_frames if _safe_float(frame.get("f0_hz"))]
    voiced_confidence = [
        float(frame.get("confidence") or 0.0) for frame in pitch_frames if _safe_float(frame.get("midi"))
    ]
    duration_seconds = float(max((len(pitch_frames) - 1) * STFT_HOP / max(sample_rate, 1), 0.0))

    key_probabilities: Dict[str, float] = {}
    key_trajectory: List[Dict[str, Any]] = []
    if voiced_midi:
        key_result = detect_key(voiced_midi, input_unit="midi")
        key_probabilities = key_result.probabilities
        if key_result.best_key:
            key_trajectory.append(
                {
                    "start": 0.0,
                    "end": duration_seconds,
                    "label": key_result.best_key,
                    "confidence": float(key_result.confidence),
                }
            )

    tessitura_payload: Dict[str, Any] = {}
    if voiced_midi:
        try:
            tessitura_payload = _serialize_tessitura_payload(
                analyze_tessitura(
                    voiced_midi,
                    weights=voiced_confidence if voiced_confidence else None,
                    return_pdf=True,
                )
            )
        except Exception as exc:
            warnings.append(f"Tessitura analysis unavailable: {exc}")

    vibrato_payload: Dict[str, Any] = {}
    try:
        vibrato = detect_vibrato(optimized.f0_hz, sample_rate=sample_rate, hop_length=STFT_HOP)
        vibrato_payload = {
            "rate_hz": float(vibrato.rate_hz),
            "depth_cents": float(vibrato.depth_cents),
            "peak_power": float(vibrato.peak_power),
            "power_ratio": float(vibrato.power_ratio),
            "valid": bool(vibrato.valid),
        }
    except Exception as exc:
        warnings.append(f"Vibrato analysis unavailable: {exc}")

    formants_payload: Dict[str, Any] = {}
    try:
        formant_track = estimate_formants_from_audio(
            mono_audio,
            sample_rate,
            hop_length=STFT_HOP,
            preprocess=False,
        )
        formants_payload = _summarize_formants(formant_track)
    except Exception as exc:
        warnings.append(f"Formant analysis unavailable: {exc}")

    phrase_payload: Dict[str, Any] = {}
    try:
        phrase_result = segment_phrases_from_audio(mono_audio, sample_rate, hop_length=STFT_HOP)
        phrase_payload = _summarize_phrases(phrase_result)
    except Exception as exc:
        warnings.append(f"Phrase segmentation unavailable: {exc}")

    pitch_errors = [
        float(frame["cents"]) for frame in pitch_frames if _safe_float(frame.get("cents")) is not None
    ]
    uncertainty = summarize_uncertainty(
        [
            {
                "metadata": {"note_frequencies_hz": voiced_f0},
                "pitch_error_cents": pitch_errors,
            }
        ]
    )

    result: Dict[str, Any] = {
        "metadata": {
            "analysis_version": "0.1.0",
            "source": "tessiture-api",
            "input_path": file_path,
            "filename": metadata.get("filename") if metadata else None,
            "content_type": metadata.get("content_type") if metadata else None,
            "input_type": metadata.get("source") if metadata else "upload",
            "example_id": metadata.get("example_id") if metadata else None,
            "original_filename": metadata.get("original_filename") if metadata else None,
            "sample_rate": sample_rate,
            "hop_length": STFT_HOP,
            "frame_rate": float(sample_rate / max(STFT_HOP, 1)),
            "duration_seconds": duration_seconds,
        },
        "pitch": {
            "frames": pitch_frames,
            "f0_min": float(np.min(voiced_f0)) if voiced_f0 else None,
            "f0_max": float(np.max(voiced_f0)) if voiced_f0 else None,
        },
        "pitch_frames": pitch_frames,
        "notes": {"events": note_events},
        "note_events": note_events,
        "chords": {"timeline": chord_timeline},
        "keys": {
            "trajectory": key_trajectory,
            "probabilities": key_probabilities,
        },
        "tessitura": tessitura_payload,
        "advanced": {
            "vibrato": vibrato_payload,
            "formants": formants_payload,
            "phrase_segmentation": phrase_payload,
        },
        "uncertainty": uncertainty,
    }
    result["summary"] = _build_summary(result, duration_seconds)

    artifact_stem = f"{Path(file_path).stem}_{uuid4().hex[:10]}"
    json_path = OUTPUT_DIR / f"{artifact_stem}.json"
    csv_path = OUTPUT_DIR / f"{artifact_stem}.csv"
    pdf_path = OUTPUT_DIR / f"{artifact_stem}.pdf"

    generated_files: Dict[str, str] = {}
    generate_json_report(result, output_path=str(json_path))
    generated_files["json"] = str(json_path)

    generate_csv_report(result, output_path=str(csv_path))
    generated_files["csv"] = str(csv_path)

    try:
        generate_pdf_report(result, output_path=str(pdf_path))
        generated_files["pdf"] = str(pdf_path)
    except Exception as exc:
        warnings.append(f"PDF report unavailable: {exc}")

    result["files"] = generated_files
    result["result_path"] = generated_files.get("json")
    if warnings:
        result["warnings"] = warnings
    return result


async def analysis_pipeline(
    file_path: str,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return _run_analysis_pipeline(file_path=file_path, metadata=metadata)


@router.get("/examples")
def list_example_tracks() -> Dict[str, Any]:
    examples = _list_available_example_tracks()
    logger.info("example_gallery.endpoint_response available_examples=%d", len(examples))
    return {"examples": examples}


@router.post("/analyze/example")
async def analyze_example_audio(
    request: Request,
    example_id: str = Query(..., min_length=1),
) -> Dict[str, Any]:
    _rate_limit_check(request)
    example, file_path = _resolve_example_track(example_id)
    job_id = job_manager.create_job(
        str(file_path),
        analysis_pipeline,
        metadata={
            "filename": example["display_name"],
            "content_type": example["content_type"],
            "source": "example",
            "example_id": example["id"],
            "original_filename": example["filename"],
        },
    )
    return {
        "job_id": job_id,
        "status_url": f"/status/{job_id}",
        "results_url": f"/results/{job_id}",
    }


@router.post("/analyze")
async def analyze_audio(request: Request, audio: UploadFile = File(...)) -> Dict[str, Any]:
    _rate_limit_check(request)
    file_path = await _save_upload(audio)
    job_id = job_manager.create_job(
        str(file_path),
        analysis_pipeline,
        metadata={"filename": audio.filename, "content_type": audio.content_type, "source": "upload"},
    )
    return {
        "job_id": job_id,
        "status_url": f"/status/{job_id}",
        "results_url": f"/results/{job_id}",
    }


@router.get("/status/{job_id}")
def get_status(job_id: str) -> Dict[str, Any]:
    job = job_manager.get_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _serialize_status(job)


@router.get("/results/{job_id}")
def get_results(
    job_id: str,
    format: str = Query("json", pattern="^(json|csv|pdf)$"),
) -> Any:
    job = job_manager.get_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job not completed (status={job.status}).")
    result = job_manager.get_result(job_id) or {}
    if format == "json":
        return result
    if not isinstance(result, Mapping):
        raise HTTPException(status_code=404, detail=f"No {format} result available.")
    result_path = _extract_result_path(result, format)
    if not result_path:
        raise HTTPException(status_code=404, detail=f"No {format} result available.")
    file_path = Path(result_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"{format.upper()} output not found.")
    media_type = "text/csv" if format == "csv" else "application/pdf"
    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )
