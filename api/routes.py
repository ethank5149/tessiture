from __future__ import annotations

import asyncio
from functools import lru_cache
import logging
import mimetypes
import os
import re
import time
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

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
from analysis.comparison import reference_cache as _ref_cache
from analysis.dsp.vocal_separation import is_available as _vocal_separation_available
from api import job_manager
from calibration.monte_carlo.uncertainty_analyzer import summarize_uncertainty
from calibration.reference_generation.lhs_sampler import lhs_sample
from calibration.reference_generation.parameter_ranges import get_default_parameter_ranges
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
NOTE_EVENT_MIN_CONFIDENCE = float(os.getenv("TESSITURE_NOTE_EVENT_MIN_CONFIDENCE", "0.15"))
NOTE_EVENT_MIN_FRAMES = int(os.getenv("TESSITURE_NOTE_EVENT_MIN_FRAMES", "3"))
NOTE_EVENT_SPLIT_HYSTERESIS_MIDI = float(os.getenv("TESSITURE_NOTE_EVENT_SPLIT_HYSTERESIS_MIDI", "0.45"))
BOOTSTRAP_SAMPLES = int(os.getenv("TESSITURE_BOOTSTRAP_SAMPLES", "1000"))
BOOTSTRAP_CONFIDENCE_LEVEL = float(os.getenv("TESSITURE_BOOTSTRAP_CONFIDENCE_LEVEL", "0.95"))
REFERENCE_CALIBRATION_SAMPLE_COUNT = int(os.getenv("TESSITURE_REFERENCE_CALIBRATION_SAMPLES", "24"))
REFERENCE_CALIBRATION_SEED = int(os.getenv("TESSITURE_REFERENCE_CALIBRATION_SEED", "20260303"))
DEFAULT_INFERENTIAL_PRESET = os.getenv("TESSITURE_INFERENTIAL_PRESET", "casual").strip().lower()
INFERENTIAL_NULL_PRESETS: Dict[str, Dict[str, float]] = {
    "casual": {
        "f0_mean_hz": 196.0,
        "f0_min_hz": 130.81,
        "f0_max_hz": 440.0,
        "tessitura_center_midi": 57.0,
        "pitch_error_mean_cents": 0.0,
    },
    "intermediate": {
        "f0_mean_hz": 220.0,
        "f0_min_hz": 130.81,
        "f0_max_hz": 523.25,
        "tessitura_center_midi": 60.0,
        "pitch_error_mean_cents": 0.0,
    },
    "vocalist": {
        "f0_mean_hz": 246.94,
        "f0_min_hz": 146.83,
        "f0_max_hz": 659.25,
        "tessitura_center_midi": 64.0,
        "pitch_error_mean_cents": 0.0,
    },
}

# Rate limiting placeholder (token bucket per client IP).
RATE_LIMIT_CAPACITY = int(os.getenv("TESSITURE_RATE_LIMIT_CAPACITY", "10"))
RATE_LIMIT_REFILL_PER_SEC = float(os.getenv("TESSITURE_RATE_LIMIT_REFILL_PER_SEC", "0.5"))
_RATE_LIMIT_BUCKETS: Dict[str, Dict[str, float]] = {}

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

EXAMPLE_CONTENT_TYPE_OVERRIDES: Dict[str, str] = {
    ".opus": "audio/opus",
    ".m4a": "audio/mp4",
}
EXAMPLE_IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp"}


# Voiced-frame filter thresholds — aligned with compute_voicing_mask defaults.
# Frames outside these bounds are noise/artifact detections, not genuine pitch.
_VOICED_MIN_HZ: float = float(os.getenv("TESSITURE_VOICED_MIN_HZ", "80.0"))
_VOICED_MAX_HZ: float = float(os.getenv("TESSITURE_VOICED_MAX_HZ", "1200.0"))
_VOICED_MIN_SALIENCE: float = float(os.getenv("TESSITURE_VOICED_MIN_SALIENCE", "0.3"))

# Vocal separation configuration
_VOCAL_SEPARATION_MODE: str = os.getenv("TESSITURE_VOCAL_SEPARATION", "auto").lower()
_STEM_CACHE_DIR: Optional[Path] = (
    Path(os.getenv("TESSITURE_STEM_CACHE_DIR", "/data/stem_cache"))
    if os.getenv("TESSITURE_STEM_CACHE_DIR") or _VOCAL_SEPARATION_MODE != "off"
    else None
)


def _is_voiced_frame(frame: Mapping[str, Any]) -> bool:
    """Return True only for frames that pass frequency-range and confidence checks.

    Mirrors the logic in :func:`analysis.pitch.estimator.compute_voicing_mask`
    so that voiced_f0 collections in the pipeline stay free of artifact extremes.
    """
    f0 = _safe_float(frame.get("f0_hz") or frame.get("f0"))
    if f0 is None or not (_VOICED_MIN_HZ <= f0 <= _VOICED_MAX_HZ):
        return False
    confidence = _safe_float(frame.get("confidence") or frame.get("salience"))
    return confidence is not None and confidence >= _VOICED_MIN_SALIENCE


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _build_example_payload(example: Mapping[str, Any], file_path: Path) -> Dict[str, Any]:
    return {
        "id": str(example.get("id") or ""),
        "display_name": str(example.get("display_name") or file_path.stem),
        "title": str(example.get("title") or file_path.stem),
        "artist": example.get("artist"),
        "album": example.get("album"),
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


_FILENAME_DELIMITER = " - "


def _parse_example_stem(stem: str) -> Dict[str, Optional[str]]:
    """Parse artist, optional album, and title from an example filename stem.

    Filename schema (delimiter is ' - '):
        Title                        → title only
        Artist - Title               → artist + title
        Artist - Album - Title       → artist + album + title
        Artist - A - B - Title       → artist + album('A - B') + title
    """
    parts = stem.split(_FILENAME_DELIMITER)
    if len(parts) == 1:
        return {"artist": None, "album": None, "title": parts[0].strip()}
    if len(parts) == 2:
        return {"artist": parts[0].strip(), "album": None, "title": parts[1].strip()}
    return {
        "artist": parts[0].strip(),
        "album": _FILENAME_DELIMITER.join(parts[1:-1]).strip(),
        "title": parts[-1].strip(),
    }


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

        parsed = _parse_example_stem(candidate.stem)
        example_payload = {
            "id": example_id,
            "display_name": candidate.stem,
            "title": parsed["title"],
            "artist": parsed["artist"],
            "album": parsed["album"],
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
    stage = job.stage or job.status
    message = job.message
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "stage": stage,
        "message": message,
        "detail": message,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "result_path": job.result_path,
        "error": _sanitize_error(job.error),
    }


def _sanitize_error(error: Optional[str]) -> Optional[str]:
    if error is None:
        return None
    text = str(error).strip()
    if not text:
        return "Analysis failed."
    if "Traceback (most recent call last):" in text:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            tail = lines[-1]
            if ":" in tail:
                _, detail = tail.split(":", 1)
                detail = detail.strip()
                if detail:
                    return detail
        return "Analysis failed."
    if "\n" in text:
        return text.splitlines()[0].strip() or "Analysis failed."
    return text


def _extract_result_path(result: Mapping[str, Any], fmt: str) -> Optional[str]:
    if not isinstance(result, Mapping):
        return None

    search_spaces: List[Mapping[str, Any]] = [result]
    nested_analysis = result.get("analysis")
    if isinstance(nested_analysis, Mapping):
        search_spaces.append(nested_analysis)

    for payload in search_spaces:
        files = payload.get("files")
        if isinstance(files, Mapping) and files.get(fmt):
            return str(files.get(fmt))
        key = f"{fmt}_path"
        if payload.get(key):
            return str(payload.get(key))

    if fmt == "json":
        for payload in search_spaces:
            if payload.get("result_path"):
                return str(payload.get("result_path"))

    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _as_finite_array(values: Sequence[Any]) -> np.ndarray:
    numeric: List[float] = []
    for value in values:
        number = _safe_float(value)
        if number is None:
            continue
        numeric.append(float(number))
    return np.asarray(numeric, dtype=float)


@lru_cache(maxsize=1)
def _build_reference_calibration_uncertainty() -> Dict[str, Any]:
    try:
        parameter_ranges = dict(get_default_parameter_ranges())
        parameter_ranges["note_count"] = (1.0, 1.0)
        parameter_ranges["duration_s"] = (0.1, 0.1)

        sampled_params = lhs_sample(
            max(1, REFERENCE_CALIBRATION_SAMPLE_COUNT),
            parameter_ranges,
            seed=REFERENCE_CALIBRATION_SEED,
        )

        reference_results: List[Dict[str, Any]] = []
        for params in sampled_params:
            f0_hz = _safe_float(params.get("f0_hz"))
            detune_cents = _safe_float(params.get("detune_cents")) or 0.0
            if f0_hz is None or f0_hz <= 0.0:
                continue

            note_frequency_hz = float(f0_hz * (2.0 ** (detune_cents / 1200.0)))
            modeled_pitch_error_cents = float(0.9 * detune_cents)
            reference_results.append(
                {
                    "metadata": {"note_frequencies_hz": [note_frequency_hz]},
                    "pitch_error_cents": [modeled_pitch_error_cents],
                }
            )

        uncertainty = summarize_uncertainty(reference_results)
    except Exception:
        logger.warning("reference_calibration_uncertainty_build_failed", exc_info=True)
        uncertainty = summarize_uncertainty([])
        reference_results = []

    uncertainty["reference_source"] = "generated_ground_truth_reference"
    uncertainty["reference_seed"] = REFERENCE_CALIBRATION_SEED
    uncertainty["reference_dataset_size"] = len(reference_results)
    uncertainty["reference_voiced_frame_count"] = len(reference_results)
    return uncertainty


def _resolve_inferential_preset(metadata: Optional[Mapping[str, Any]]) -> tuple[str, Dict[str, float]]:
    requested = None
    if isinstance(metadata, Mapping):
        requested = metadata.get("inferential_preset")
    preset = str(requested or DEFAULT_INFERENTIAL_PRESET).strip().lower()
    if preset not in INFERENTIAL_NULL_PRESETS:
        logger.warning("inferential_preset_unknown preset=%s fallback=%s", preset, DEFAULT_INFERENTIAL_PRESET)
        preset = DEFAULT_INFERENTIAL_PRESET if DEFAULT_INFERENTIAL_PRESET in INFERENTIAL_NULL_PRESETS else "casual"
    return preset, dict(INFERENTIAL_NULL_PRESETS[preset])


def _bootstrap_two_sided_p_value(replicates: np.ndarray, null_value: Optional[float]) -> Optional[float]:
    if null_value is None or replicates.size == 0:
        return None
    left_tail = float(np.mean(replicates <= float(null_value)))
    right_tail = float(np.mean(replicates >= float(null_value)))
    return float(np.clip(2.0 * min(left_tail, right_tail), 0.0, 1.0))


def _build_metric_inference(
    metric_name: str,
    values: np.ndarray,
    reducer: Callable[[np.ndarray], float],
    null_value: Optional[float],
    unit: str,
    confidence_level: float,
    bootstrap_samples: int,
    rng: np.random.Generator,
) -> Dict[str, Any]:
    logger.debug(
        "analysis_metric_inference_build_start metric=%s n_values=%d confidence_level=%.3f bootstrap_samples=%d unit=%s null_value=%s",
        metric_name,
        int(values.size),
        float(confidence_level),
        int(bootstrap_samples),
        unit,
        null_value,
    )

    if values.size == 0:
        payload: Dict[str, Any] = {
            "estimate": None,
            "confidence_interval": {
                "level": confidence_level,
                "low": None,
                "high": None,
            },
            "p_value": None,
            "null_hypothesis": {
                "value": null_value,
                "description": f"{metric_name} equals {null_value}",
            },
            "n_samples": 0,
            "unit": unit,
        }
        logger.debug("analysis_metric_inference_build_empty metric=%s", metric_name)
        return payload

    samples = np.asarray(values, dtype=float)
    sample_size = int(samples.size)
    estimate = float(reducer(samples))

    replicates = np.empty(int(bootstrap_samples), dtype=float)
    for idx in range(int(bootstrap_samples)):
        sampled = rng.choice(samples, size=sample_size, replace=True)
        replicates[idx] = float(reducer(sampled))

    tail = (1.0 - float(confidence_level)) / 2.0
    ci_low = float(np.quantile(replicates, tail))
    ci_high = float(np.quantile(replicates, 1.0 - tail))

    payload: Dict[str, Any] = {
        "estimate": estimate,
        "confidence_interval": {
            "level": confidence_level,
            "low": ci_low,
            "high": ci_high,
        },
        "p_value": _bootstrap_two_sided_p_value(replicates, null_value),
        "null_hypothesis": {
            "value": null_value,
            "description": f"{metric_name} equals {null_value}",
        },
        "n_samples": sample_size,
        "unit": unit,
    }

    logger.debug(
        "analysis_metric_inference_build_done metric=%s estimate=%s ci_low=%s ci_high=%s p_value=%s n_sample=%d",
        metric_name,
        payload.get("estimate"),
        payload.get("confidence_interval", {}).get("low"),
        payload.get("confidence_interval", {}).get("high"),
        payload.get("p_value"),
        sample_size,
    )
    return payload


def _build_inferential_statistics(
    voiced_f0: Sequence[float],
    voiced_midi: Sequence[float],
    pitch_errors: Sequence[float],
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    preset_name, nulls = _resolve_inferential_preset(metadata)
    confidence_level = float(np.clip(BOOTSTRAP_CONFIDENCE_LEVEL, 0.5, 0.999))
    bootstrap_samples = max(200, int(BOOTSTRAP_SAMPLES))
    rng = np.random.default_rng(20260302)

    voiced_f0_arr = _as_finite_array(voiced_f0)
    voiced_midi_arr = _as_finite_array(voiced_midi)
    pitch_error_arr = _as_finite_array(pitch_errors)

    metrics = {
        "f0_mean_hz": _build_metric_inference(
            "f0_mean_hz",
            voiced_f0_arr,
            lambda data: float(np.mean(data)),
            nulls.get("f0_mean_hz"),
            "Hz",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
        "f0_min_hz": _build_metric_inference(
            "f0_min_hz",
            voiced_f0_arr,
            lambda data: float(np.min(data)),
            nulls.get("f0_min_hz"),
            "Hz",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
        "f0_max_hz": _build_metric_inference(
            "f0_max_hz",
            voiced_f0_arr,
            lambda data: float(np.max(data)),
            nulls.get("f0_max_hz"),
            "Hz",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
        "tessitura_center_midi": _build_metric_inference(
            "tessitura_center_midi",
            voiced_midi_arr,
            lambda data: float(np.mean(data)),
            nulls.get("tessitura_center_midi"),
            "MIDI",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
        "pitch_error_mean_cents": _build_metric_inference(
            "pitch_error_mean_cents",
            pitch_error_arr,
            lambda data: float(np.mean(data)),
            nulls.get("pitch_error_mean_cents"),
            "cents",
            confidence_level,
            bootstrap_samples,
            rng,
        ),
    }

    # Add note-name annotations for pitch-unit metrics (Hz, MIDI).
    for payload in metrics.values():
        if not isinstance(payload, Mapping):
            continue
        unit = payload.get("unit")
        if not _unit_supports_pitch_note_names(unit):
            continue

        estimate_note = _pitch_value_to_note_name(payload.get("estimate"), unit)
        if estimate_note is not None:
            payload["estimate_note"] = estimate_note

        confidence_interval = payload.get("confidence_interval")
        if isinstance(confidence_interval, Mapping):
            low_note = _pitch_value_to_note_name(confidence_interval.get("low"), unit)
            high_note = _pitch_value_to_note_name(confidence_interval.get("high"), unit)
            if low_note is not None:
                confidence_interval["low_note"] = low_note
            if high_note is not None:
                confidence_interval["high_note"] = high_note

        null_hypothesis = payload.get("null_hypothesis")
        if isinstance(null_hypothesis, Mapping):
            value_note = _pitch_value_to_note_name(null_hypothesis.get("value"), unit)
            if value_note is not None:
                null_hypothesis["value_note"] = value_note

    for metric_name, payload in metrics.items():
        ci = payload.get("confidence_interval") if isinstance(payload, Mapping) else None
        logger.info(
            "analysis_metric_inference metric=%s preset=%s estimate=%s ci_low=%s ci_high=%s p_value=%s n_sample=%s",
            metric_name,
            preset_name,
            payload.get("estimate") if isinstance(payload, Mapping) else None,
            ci.get("low") if isinstance(ci, Mapping) else None,
            ci.get("high") if isinstance(ci, Mapping) else None,
            payload.get("p_value") if isinstance(payload, Mapping) else None,
            payload.get("n_samples") if isinstance(payload, Mapping) else None,
        )

    return {
        "preset": preset_name,
        "confidence_level": confidence_level,
        "bootstrap_samples": bootstrap_samples,
        "metrics": metrics,
    }


def _build_calibration_summary(
    uncertainty: Mapping[str, Any],
) -> Dict[str, Any]:
    uncertainty_payload = uncertainty if isinstance(uncertainty, Mapping) else {}

    frequency_bins = _as_finite_array(uncertainty_payload.get("frequency_bins_hz") or [])
    sample_counts = _as_finite_array(uncertainty_payload.get("sample_counts") or [])
    pitch_bias = _as_finite_array(uncertainty_payload.get("pitch_bias_cents") or [])
    pitch_variance = _as_finite_array(uncertainty_payload.get("pitch_variance_cents2") or [])

    def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> Optional[float]:
        size = min(values.size, weights.size)
        if size <= 0:
            return None
        safe_weights = np.clip(weights[:size], 0.0, None)
        total = float(np.sum(safe_weights))
        if total <= 0.0:
            return None
        return float(np.sum(values[:size] * safe_weights) / total)

    paired_bias_size = min(pitch_bias.size, sample_counts.size)
    paired_variance_size = min(pitch_variance.size, sample_counts.size)
    paired_moment_size = min(pitch_bias.size, pitch_variance.size, sample_counts.size)

    bias_values = pitch_bias[:paired_bias_size]
    bias_counts = sample_counts[:paired_bias_size]
    variance_values = pitch_variance[:paired_variance_size]
    variance_counts = sample_counts[:paired_variance_size]
    moment_bias_values = pitch_bias[:paired_moment_size]
    moment_variance_values = pitch_variance[:paired_moment_size]
    moment_counts = sample_counts[:paired_moment_size]

    populated_bins = sample_counts[sample_counts > 0.0]
    populated_bias_mask = bias_counts > 0.0

    mean_pitch_bias = _weighted_mean(bias_values, bias_counts)
    mean_pitch_variance = _weighted_mean(variance_values, variance_counts)
    max_abs_pitch_bias = (
        float(np.max(np.abs(bias_values[populated_bias_mask])))
        if bias_values.size and np.any(populated_bias_mask)
        else None
    )

    pitch_error_std: Optional[float] = None
    populated_moment_mask = moment_counts > 0.0
    if moment_bias_values.size and np.any(populated_moment_mask):
        weights = np.clip(moment_counts[populated_moment_mask], 0.0, None)
        total = float(np.sum(weights))
        if total > 0.0 and mean_pitch_bias is not None:
            centered = moment_bias_values[populated_moment_mask] - float(mean_pitch_bias)
            second_moment = np.sum(
                weights * (moment_variance_values[populated_moment_mask] + np.square(centered))
            ) / total
            pitch_error_std = float(np.sqrt(max(float(second_moment), 0.0)))

    reference_sample_count = (
        int(round(float(np.sum(np.clip(sample_counts, 0.0, None))))) if sample_counts.size else 0
    )

    mean_frame_uncertainty = _safe_float(uncertainty_payload.get("reference_mean_frame_uncertainty_midi"))

    voiced_frame_count_value = _safe_float(uncertainty_payload.get("reference_voiced_frame_count"))
    voiced_frame_count = (
        int(round(voiced_frame_count_value)) if voiced_frame_count_value is not None else reference_sample_count
    )

    return {
        "source": str(uncertainty_payload.get("reference_source") or "generated_ground_truth_reference"),
        "reference_sample_count": reference_sample_count,
        "reference_frequency_min_hz": float(np.min(frequency_bins)) if frequency_bins.size else None,
        "reference_frequency_max_hz": float(np.max(frequency_bins)) if frequency_bins.size else None,
        "frequency_bin_count": int(max(frequency_bins.size - 1, 0)),
        "populated_frequency_bin_count": int(populated_bins.size),
        "mean_pitch_bias_cents": mean_pitch_bias,
        "max_abs_pitch_bias_cents": max_abs_pitch_bias,
        "mean_pitch_variance_cents2": mean_pitch_variance,
        "pitch_error_mean_cents": mean_pitch_bias,
        "pitch_error_std_cents": pitch_error_std,
        "mean_frame_uncertainty_midi": mean_frame_uncertainty,
        "voiced_frame_count": voiced_frame_count,
    }


def _midi_to_note_name(midi_value: float) -> str:
    rounded = int(round(float(midi_value)))
    note_index = rounded % 12
    octave = rounded // 12 - 1
    return f"{NOTE_NAMES[note_index]}{octave}"


def _hz_to_note_name(frequency_hz: Any) -> Optional[str]:
    frequency = _safe_float(frequency_hz)
    if frequency is None or frequency <= 0.0:
        return None
    midi_value = 69.0 + 12.0 * float(np.log2(frequency / 440.0))
    return _midi_to_note_name(midi_value)


def _unit_supports_pitch_note_names(unit: Any) -> bool:
    return str(unit or "").strip().upper() in {"HZ", "MIDI"}


def _pitch_value_to_note_name(value: Any, unit: Any) -> Optional[str]:
    unit_upper = str(unit or "").strip().upper()
    if unit_upper == "MIDI":
        midi_value = _safe_float(value)
        return _midi_to_note_name(midi_value) if midi_value is not None else None
    if unit_upper == "HZ":
        return _hz_to_note_name(value)
    return None


def _midi_values_to_note_names(values: Sequence[Any]) -> List[Optional[str]]:
    notes: List[Optional[str]] = []
    for value in values:
        midi_value = _safe_float(value)
        notes.append(_midi_to_note_name(midi_value) if midi_value is not None else None)
    return notes


def _normalize_analysis_diagnostics(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return None

    attempted_raw = payload.get("attempted_methods")
    attempted_methods = (
        [str(item) for item in attempted_raw if isinstance(item, (str, int, float))]
        if isinstance(attempted_raw, Sequence) and not isinstance(attempted_raw, (str, bytes))
        else []
    )

    strategy_path = payload.get("strategy_path")
    fallback_reason = payload.get("fallback_reason")

    return {
        "primary_method_used": str(payload.get("primary_method_used") or "unknown"),
        "attempted_methods": attempted_methods,
        "strategy_path": str(strategy_path) if strategy_path is not None else None,
        "fallback_reason": str(fallback_reason) if fallback_reason is not None else None,
    }


def _extract_pitch_frame_diagnostics(pitch_candidates: Sequence[Any]) -> List[Optional[Dict[str, Any]]]:
    diagnostics: List[Optional[Dict[str, Any]]] = []
    for frame in pitch_candidates:
        components = getattr(frame, "components", None)
        diag_payload = components.get("analysis_diagnostics") if isinstance(components, Mapping) else None
        diagnostics.append(_normalize_analysis_diagnostics(diag_payload))
    return diagnostics


def _summarize_pitch_method_diagnostics(
    frame_diagnostics: Sequence[Optional[Mapping[str, Any]]],
) -> Dict[str, Any]:
    method_counts: Dict[str, int] = {}
    fallback_reasons: Dict[str, int] = {}
    attempted_methods: List[str] = []
    strategy_path: Optional[str] = None

    for diag in frame_diagnostics:
        if not isinstance(diag, Mapping):
            continue

        method = str(diag.get("primary_method_used") or "unknown")
        method_counts[method] = method_counts.get(method, 0) + 1

        fallback_reason = diag.get("fallback_reason")
        if fallback_reason:
            reason = str(fallback_reason)
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1

        if not attempted_methods:
            attempted = diag.get("attempted_methods")
            if isinstance(attempted, Sequence) and not isinstance(attempted, (str, bytes)):
                attempted_methods = [str(item) for item in attempted if isinstance(item, (str, int, float))]

        if strategy_path is None:
            strategy = diag.get("strategy_path")
            if strategy is not None:
                strategy_path = str(strategy)

    primary_method_used = max(method_counts, key=method_counts.get) if method_counts else None
    fallback_reason = max(fallback_reasons, key=fallback_reasons.get) if fallback_reasons else None

    return {
        "primary_method_used": primary_method_used,
        "attempted_methods": attempted_methods,
        "strategy_path": strategy_path,
        "fallback_reason": fallback_reason,
        "method_counts": method_counts,
        "fallback_reasons": fallback_reasons,
        "frames_with_diagnostics": int(sum(1 for diag in frame_diagnostics if isinstance(diag, Mapping))),
    }


def _build_pitch_payload(
    f0_hz: np.ndarray,
    salience: np.ndarray,
    midi_values: np.ndarray,
    midi_sigma: np.ndarray,
    *,
    sample_rate: int,
    hop_length: int,
    frame_diagnostics: Optional[Sequence[Optional[Mapping[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    f0_values = np.asarray(f0_hz, dtype=float)
    salience_values = np.asarray(salience, dtype=float)
    midi = np.asarray(midi_values, dtype=float)
    midi_uncertainty = np.asarray(midi_sigma, dtype=float)

    frame_count = int(max(f0_values.size, salience_values.size, midi.size, midi_uncertainty.size))
    frames: List[Dict[str, Any]] = []
    seconds_per_frame = float(hop_length) / float(max(sample_rate, 1))

    for idx in range(frame_count):
        f0_value = _safe_float(f0_values[idx] if idx < f0_values.size else None)
        salience_value = _safe_float(salience_values[idx] if idx < salience_values.size else None)
        midi_value = _safe_float(midi[idx] if idx < midi.size else None)
        uncertainty_value = _safe_float(midi_uncertainty[idx] if idx < midi_uncertainty.size else None)

        if midi_value is not None and midi_value <= 0.0:
            midi_value = None

        confidence = float(np.clip(salience_value if salience_value is not None else 0.0, 0.0, 1.0))
        cents = float((midi_value - round(midi_value)) * 100.0) if midi_value is not None else None
        note_name = _midi_to_note_name(midi_value) if midi_value is not None else None

        frame_payload: Dict[str, Any] = {
            "index": idx,
            "time": float(idx) * seconds_per_frame,
            "f0_hz": f0_value,
            "f0": f0_value,
            "midi": midi_value,
            "note": note_name,
            "note_name": note_name,
            "cents": cents,
            "confidence": confidence,
            "uncertainty": float(max(uncertainty_value, 0.0)) if uncertainty_value is not None else 0.0,
            "salience": salience_value,
        }
        if frame_diagnostics is not None and idx < len(frame_diagnostics):
            normalized_diag = _normalize_analysis_diagnostics(frame_diagnostics[idx])
            if normalized_diag is not None:
                frame_payload["analysis_diagnostics"] = normalized_diag

        frames.append(frame_payload)

    return frames


def _build_note_events(frames: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    start_idx: Optional[int] = None
    active_values: List[float] = []
    active_confidence: List[float] = []
    min_event_frames = max(int(NOTE_EVENT_MIN_FRAMES), 1)

    def _reset_active() -> None:
        nonlocal start_idx, active_values, active_confidence
        start_idx = None
        active_values = []
        active_confidence = []

    def _close_event(end_idx: int) -> None:
        if start_idx is None or not active_values:
            _reset_active()
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
                "note_name": _midi_to_note_name(midi_mean),
                "confidence": confidence,
            }
        )
        _reset_active()

    for idx, frame in enumerate(frames):
        midi_value = _safe_float(frame.get("midi"))
        confidence_value = _safe_float(frame.get("confidence")) or 0.0

        if midi_value is None or confidence_value < NOTE_EVENT_MIN_CONFIDENCE:
            if start_idx is not None:
                _close_event(idx - 1)
            continue

        if start_idx is None:
            start_idx = idx
            active_values.append(midi_value)
            active_confidence.append(confidence_value)
            continue

        lookback_count = min(len(active_values), min_event_frames)
        active_center = float(np.mean(np.asarray(active_values[-lookback_count:], dtype=float)))
        active_note = int(round(active_center))
        current_note = int(round(midi_value))
        should_split = (
            current_note != active_note
            and abs(midi_value - active_center) >= NOTE_EVENT_SPLIT_HYSTERESIS_MIDI
            and len(active_values) >= min_event_frames
        )

        if should_split:
            _close_event(idx - 1)
            start_idx = idx
            active_values.append(midi_value)
            active_confidence.append(confidence_value)
            continue

        active_values.append(midi_value)
        active_confidence.append(confidence_value)

    if start_idx is not None:
        _close_event(len(frames) - 1)

    return events


def _format_timestamp_label(seconds: Any) -> str:
    """Format seconds as MM:SS timestamp label."""
    timestamp = _safe_float(seconds)
    if timestamp is None or timestamp < 0.0:
        return "00:00"
    rounded_seconds = int(float(np.floor(float(timestamp))))
    minutes = rounded_seconds // 60
    remainder = rounded_seconds % 60
    return f"{minutes:02d}:{remainder:02d}"


def _build_evidence_payload(
    pitch_frames: Sequence[Mapping[str, Any]],
    *,
    note_events: Sequence[Mapping[str, Any]],
    duration_seconds: float,
) -> Dict[str, Any]:
    """Build additive evidence payload with low/high note references and guidance items."""
    evidence: Dict[str, Any] = {
        "events": [],
        "guidance": [],
        "lowest_voiced_note_ref": None,
        "highest_voiced_note_ref": None,
        "note_event_count": int(len(note_events)),
    }

    voiced_frames_data: List[Dict[str, float]] = []
    for idx, frame in enumerate(pitch_frames):
        if not isinstance(frame, Mapping) or not _is_voiced_frame(frame):
            continue

        time_s = _safe_float(frame.get("time"))
        if time_s is None:
            time_s = float(idx)

        midi_value = _safe_float(frame.get("midi"))
        f0_hz = _safe_float(frame.get("f0_hz") or frame.get("f0"))
        if midi_value is None and f0_hz is not None and f0_hz > 0.0:
            midi_value = 69.0 + 12.0 * float(np.log2(f0_hz / 440.0))
        if midi_value is None:
            continue

        voiced_frames_data.append(
            {
                "time": float(max(time_s, 0.0)),
                "midi": float(midi_value),
                "f0_hz": float(f0_hz) if f0_hz is not None else 0.0,
                "confidence": float(_safe_float(frame.get("confidence")) or 0.0),
            }
        )

    if not voiced_frames_data:
        return evidence

    appended_events: List[Dict[str, Any]] = []

    def _add_event(event_id: str, label: str, timestamp_s: float, **extra: Any) -> Dict[str, Any]:
        safe_timestamp = float(max(_safe_float(timestamp_s) or 0.0, 0.0))
        payload: Dict[str, Any] = {
            "id": event_id,
            "label": label,
            "timestamp_s": safe_timestamp,
            "timestamp_label": _format_timestamp_label(safe_timestamp),
        }
        payload.update(extra)
        appended_events.append(payload)
        return payload

    lowest_frame = min(voiced_frames_data, key=lambda f: f["midi"])
    highest_frame = max(voiced_frames_data, key=lambda f: f["midi"])

    lowest_event = _add_event(
        "lowest_voiced_note",
        "Lowest voiced note",
        lowest_frame["time"],
        note=_midi_to_note_name(lowest_frame["midi"]),
        midi=lowest_frame["midi"],
        f0_hz=lowest_frame["f0_hz"],
        confidence=lowest_frame["confidence"],
    )
    highest_event = _add_event(
        "highest_voiced_note",
        "Highest voiced note",
        highest_frame["time"],
        note=_midi_to_note_name(highest_frame["midi"]),
        midi=highest_frame["midi"],
        f0_hz=highest_frame["f0_hz"],
        confidence=highest_frame["confidence"],
    )

    evidence["lowest_voiced_note_ref"] = lowest_event["id"]
    evidence["highest_voiced_note_ref"] = highest_event["id"]

    safe_duration = _safe_float(duration_seconds)
    if safe_duration is None or safe_duration <= 0.0:
        safe_duration = max(f["time"] for f in voiced_frames_data)
    safe_duration = max(float(safe_duration), 1e-6)

    segment_labels = ("Start", "Middle", "End")
    segment_stats: List[Dict[str, Any]] = [
        {"label": lbl, "count": 0, "weight": 0.0, "first_time": None}
        for lbl in segment_labels
    ]
    for vf in voiced_frames_data:
        normalized = float(np.clip(vf["time"] / safe_duration, 0.0, 0.999999))
        seg_idx = int(normalized * len(segment_labels))
        seg_idx = min(seg_idx, len(segment_labels) - 1)
        seg = segment_stats[seg_idx]
        seg["count"] += 1
        seg["weight"] += vf["confidence"] if vf["confidence"] > 0.0 else 1.0
        if seg["first_time"] is None:
            seg["first_time"] = vf["time"]

    peak_segment = max(segment_stats, key=lambda s: (s["count"], s["weight"]))
    peak_segment_event = _add_event(
        "segment_peak_voiced_activity",
        "Peak voiced activity segment",
        float(peak_segment["first_time"] if peak_segment["first_time"] is not None else 0.0),
        segment=peak_segment["label"],
        voiced_frame_count=int(peak_segment["count"]),
    )

    largest_jump_event: Optional[Dict[str, Any]] = None
    if len(voiced_frames_data) >= 2:
        ordered_frames = sorted(voiced_frames_data, key=lambda f: f["time"])
        best_jump: Optional[Dict[str, Any]] = None
        for prev, curr in zip(ordered_frames, ordered_frames[1:]):
            jump_midi = abs(curr["midi"] - prev["midi"])
            if best_jump is None or jump_midi > float(best_jump["delta_midi"]):
                best_jump = {
                    "delta_midi": float(jump_midi),
                    "start_s": float(prev["time"]),
                    "end_s": float(curr["time"]),
                    "from_note": _midi_to_note_name(prev["midi"]),
                    "to_note": _midi_to_note_name(curr["midi"]),
                }
        if best_jump is not None:
            largest_jump_event = _add_event(
                "largest_pitch_jump",
                "Largest pitch jump",
                best_jump["end_s"],
                start_s=best_jump["start_s"],
                end_s=best_jump["end_s"],
                delta_midi=best_jump["delta_midi"],
                from_note=best_jump["from_note"],
                to_note=best_jump["to_note"],
            )

    evidence["events"] = appended_events

    event_by_id = {e["id"]: e for e in appended_events}

    evidence["guidance"].append(
        {
            "id": "guidance_range_edges",
            "claim": "Your lowest and highest voiced notes define the current edges of this take.",
            "why": (
                f"Lowest note {lowest_event.get('note')} appears near {lowest_event.get('timestamp_label')}, "
                f"and highest note {highest_event.get('note')} appears near {highest_event.get('timestamp_label')}."
            ),
            "action": "Jump to each edge and practice smooth, relaxed transitions into and out of those notes.",
            "evidence_refs": [lowest_event["id"], highest_event["id"]],
        }
    )

    evidence["guidance"].append(
        {
            "id": "guidance_peak_segment",
            "claim": "Most voiced activity is concentrated in one section of the recording.",
            "why": (
                f"The {peak_segment_event.get('segment', 'session')} segment contains the highest concentration "
                "of voiced frames."
            ),
            "action": "Start focused practice in that segment, then repeat once after a short recovery breath.",
            "evidence_refs": [peak_segment_event["id"]],
        }
    )

    if largest_jump_event is not None:
        evidence["guidance"].append(
            {
                "id": "guidance_large_transition_control",
                "claim": "One transition has the largest pitch jump and needs extra control.",
                "why": (
                    f"A jump of about {float(largest_jump_event.get('delta_midi') or 0.0):.1f} MIDI steps occurs near "
                    f"{largest_jump_event.get('timestamp_label')}."
                ),
                "action": "Loop this transition slowly before returning to full-tempo phrasing.",
                "evidence_refs": [largest_jump_event["id"]],
            }
        )

    return evidence


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

    range_min = _safe_float(getattr(metrics, "range_min", None))
    range_max = _safe_float(getattr(metrics, "range_max", None))
    tessitura_band = list(getattr(metrics, "tessitura_band", ()))
    comfort_band = list(getattr(metrics, "comfort_band", ()))
    comfort_center = _safe_float(getattr(metrics, "comfort_center", None))

    serialized: Dict[str, Any] = {
        "metrics": {
            "count": int(getattr(metrics, "count", 0)),
            "weight_sum": _safe_float(getattr(metrics, "weight_sum", None)),
            "range_min": range_min,
            "range_max": range_max,
            "range_min_note": _midi_to_note_name(range_min) if range_min is not None else None,
            "range_max_note": _midi_to_note_name(range_max) if range_max is not None else None,
            "tessitura_band": tessitura_band,
            "tessitura_band_notes": _midi_values_to_note_names(tessitura_band),
            "comfort_band": comfort_band,
            "comfort_band_notes": _midi_values_to_note_names(comfort_band),
            "comfort_center": comfort_center,
            "comfort_center_note": _midi_to_note_name(comfort_center) if comfort_center is not None else None,
            "variance": _safe_float(getattr(metrics, "variance", None)),
            "std_dev": _safe_float(getattr(metrics, "std_dev", None)),
            "mean_variance": _safe_float(getattr(metrics, "mean_variance", None)),
            "strain_zones": strain_zones,
        }
    }

    if pdf is not None:
        density = np.asarray(getattr(pdf, "density", []), dtype=float).tolist()
        serialized["pdf"] = {
            "bin_edges": np.asarray(getattr(pdf, "bin_edges", []), dtype=float).tolist(),
            "density": density,
            "bin_centers": np.asarray(getattr(pdf, "bin_centers", []), dtype=float).tolist(),
            "bin_size": _safe_float(getattr(pdf, "bin_size", None)),
            "total_weight": _safe_float(getattr(pdf, "total_weight", None)),
        }
        # Backward-compatible aliases expected by some clients.
        serialized["histogram"] = density
        serialized["heatmap"] = density
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
    voiced_frames = [item for item in pitch_frames if _is_voiced_frame(item)]
    voiced_f0 = [float(item["f0_hz"]) for item in voiced_frames]
    confidences = [
        float(item["confidence"])
        for item in voiced_frames
        if _safe_float(item.get("confidence")) is not None
    ]
    mean_confidence = float(np.mean(confidences)) if confidences else 0.0

    tessitura_metrics = result.get("tessitura", {}).get("metrics", {}) if isinstance(result, Mapping) else {}
    tessitura_band = tessitura_metrics.get("tessitura_band") if isinstance(tessitura_metrics, Mapping) else None
    tessitura_range_notes: Optional[List[str]] = None
    if isinstance(tessitura_band, Sequence) and not isinstance(tessitura_band, (str, bytes)):
        candidate_notes = [note for note in _midi_values_to_note_names(list(tessitura_band)[:2]) if note is not None]
        if len(candidate_notes) == 2:
            tessitura_range_notes = candidate_notes
    key_trajectory = result.get("keys", {}).get("trajectory", []) if isinstance(result, Mapping) else []
    key_confidence = 0.0
    if isinstance(key_trajectory, Sequence) and key_trajectory:
        key_confidence = _safe_float(key_trajectory[0].get("confidence")) or 0.0

    logger.info(
        "analysis_confidence_summary duration=%.3fs total_frames=%d voiced_frames=%d confidence_min=%.4f confidence_max=%.4f confidence_mean=%.4f key_confidence=%.4f",
        float(duration_seconds),
        len(pitch_frames),
        len(voiced_f0),
        float(np.min(confidences)) if confidences else 0.0,
        float(np.max(confidences)) if confidences else 0.0,
        mean_confidence,
        key_confidence,
    )

    return {
        "duration_seconds": float(duration_seconds),
        "f0_min": float(np.min(voiced_f0)) if voiced_f0 else None,
        "f0_max": float(np.max(voiced_f0)) if voiced_f0 else None,
        "f0_min_note": _hz_to_note_name(np.min(voiced_f0)) if voiced_f0 else None,
        "f0_max_note": _hz_to_note_name(np.max(voiced_f0)) if voiced_f0 else None,
        "tessitura_range": tessitura_band,
        "tessitura_range_notes": tessitura_range_notes,
        "confidence": mean_confidence,
        "pitch_confidence": mean_confidence,
        "key_confidence": key_confidence,
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


def _noop_progress_update(
    _progress: int,
    _stage: Optional[str] = None,
    _message: Optional[str] = None,
) -> None:
    return


def _resolve_progress_update(
    metadata: Optional[Mapping[str, Any]],
) -> Callable[[int, Optional[str], Optional[str]], None]:
    callback = metadata.get("_progress_callback") if isinstance(metadata, Mapping) else None
    if not callable(callback):
        return _noop_progress_update

    log_context = {
        "filename": metadata.get("filename") if isinstance(metadata, Mapping) else None,
        "source": metadata.get("source") if isinstance(metadata, Mapping) else None,
        "example_id": metadata.get("example_id") if isinstance(metadata, Mapping) else None,
    }

    def _safe_progress_update(progress: int, stage: Optional[str] = None, message: Optional[str] = None) -> None:
        logger.info(
            "analysis_progress_emit progress=%s stage=%s message=%s context=%s",
            progress,
            stage,
            message,
            log_context,
        )
        try:
            callback(progress, stage, message)
        except Exception:
            logger.debug("progress_update_callback_failed", exc_info=True)

    return _safe_progress_update


def _run_analysis_pipeline(file_path: str, metadata: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    _ensure_output_dir()
    warnings: List[str] = []
    report_progress = _resolve_progress_update(metadata)
    logger.info(
        "analysis_pipeline_start file_path=%s filename=%s source=%s example_id=%s",
        file_path,
        metadata.get("filename") if isinstance(metadata, Mapping) else None,
        metadata.get("source") if isinstance(metadata, Mapping) else None,
        metadata.get("example_id") if isinstance(metadata, Mapping) else None,
    )
    report_progress(15, "preprocessing", "Decoding and preprocessing audio.")
    audio, sample_rate = _decode_audio_file(file_path)

    # Optional vocal source separation — gated by audio_type
    # Determine audio_type from metadata
    _audio_type_requested = "isolated"
    if isinstance(metadata, Mapping):
        _audio_type_requested = str(metadata.get("audio_type") or "isolated").lower().strip()
        # Example gallery tracks and reference uploads default to "mixed"
        _source = str(metadata.get("source") or "").lower()
        if _audio_type_requested == "isolated" and _source in ("example", "reference"):
            _audio_type_requested = "mixed"

    # Resolve effective audio type
    if _audio_type_requested == "auto" and _vocal_separation_available():
        from analysis.dsp.vocal_separation import detect_audio_type as _detect_audio_type
        _detected_audio_type = _detect_audio_type(audio, sample_rate)
    elif _audio_type_requested == "auto":
        _detected_audio_type = "isolated"  # can't detect without library
    else:
        _detected_audio_type = _audio_type_requested

    # Only apply separation when audio is identified as mixed and Demucs is available
    _separation_enabled = _VOCAL_SEPARATION_MODE != "off"
    _do_separate = _detected_audio_type == "mixed" and _separation_enabled and _vocal_separation_available()

    separation_info: dict = {
        "audio_type_requested": _audio_type_requested,
        "audio_type_detected": _detected_audio_type,
        "applied": False,
    }
    if _do_separate:
        try:
            from analysis.dsp.vocal_separation import separate_vocals as _separate_vocals
            report_progress(20, "vocal_separation", "Separating vocals from accompaniment.")
            sep_result = _separate_vocals(
                audio,
                sample_rate,
                file_path=file_path,
                cache_dir=_STEM_CACHE_DIR,
            )
            audio = sep_result.vocals
            sample_rate = sep_result.sample_rate
            separation_info["model"] = sep_result.model_name
            separation_info["separation_time_s"] = sep_result.separation_time_s
            separation_info["cache_hit"] = sep_result.cache_hit
            separation_info["applied"] = True
            logger.info(
                "vocal_separation_applied model=%s separation_time_s=%.2f cache_hit=%s",
                sep_result.model_name, sep_result.separation_time_s, sep_result.cache_hit,
            )
        except Exception as exc:
            warnings.append(f"Vocal separation unavailable: {exc}")
            logger.warning("vocal_separation_failed error=%s", exc, exc_info=True)

    preprocessed = preprocess_audio(
        audio,
        sample_rate=int(sample_rate),
        target_sr=TARGET_SAMPLE_RATE,
        mono=True,
        normalize=True,
    )
    mono_audio = preprocessed.audio
    sample_rate = int(preprocessed.sample_rate)

    report_progress(35, "pitch_extraction", "Extracting pitch and harmonic tracks.")
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
    pitch_frame_diagnostics = _extract_pitch_frame_diagnostics(pitch_candidates)
    pitch_method_diagnostics = _summarize_pitch_method_diagnostics(pitch_frame_diagnostics)
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
    pitch_builder_name = "_build_pitch_payload"
    pitch_builder_obj = globals().get(pitch_builder_name)
    available_builders = sorted(
        name
        for name, obj in globals().items()
        if name.startswith("_build_") and callable(obj)
    )
    logger.info(
        "analysis_metric_inference_builder_check present=%s callable=%s builder_count=%s builder_sample=%s",
        pitch_builder_name in globals(),
        callable(pitch_builder_obj),
        len(available_builders),
        available_builders[:20],
    )
    pitch_frames = _build_pitch_payload(
        optimized.f0_hz,
        optimized.salience,
        midi_values,
        midi_sigma,
        sample_rate=sample_rate,
        hop_length=STFT_HOP,
        frame_diagnostics=pitch_frame_diagnostics,
    )
    note_events = _build_note_events(pitch_frames)
    chord_timeline = _build_chord_timeline(note_events)

    report_progress(65, "advanced_analysis", "Running advanced musical and vocal analysis.")
    voiced_pitch_frames = [frame for frame in pitch_frames if _is_voiced_frame(frame)]
    voiced_midi = [
        float(frame["midi"])
        for frame in voiced_pitch_frames
        if _safe_float(frame.get("midi")) is not None
    ]
    voiced_f0 = [float(frame["f0_hz"]) for frame in voiced_pitch_frames]
    pitch_errors = [
        float(frame["cents"]) for frame in pitch_frames if _safe_float(frame.get("cents")) is not None
    ]
    frame_confidences = [
        float(frame["confidence"])
        for frame in voiced_pitch_frames
        if _safe_float(frame.get("confidence")) is not None
    ]
    frame_uncertainties = [
        float(frame["uncertainty"])
        for frame in voiced_pitch_frames
        if _safe_float(frame.get("uncertainty")) is not None
    ]
    duration_seconds = float(mono_audio.shape[-1] / max(sample_rate, 1))

    key_detection_result = detect_key(voiced_midi, input_unit="midi") if voiced_midi else None
    key_trajectory: List[Dict[str, Any]] = []
    key_probabilities: Dict[str, float] = {}
    if key_detection_result is not None:
        key_probabilities = {
            str(label): float(probability)
            for label, probability in key_detection_result.probabilities.items()
        }
        if key_detection_result.best_key:
            key_trajectory.append(
                {
                    "start": 0.0,
                    "end": duration_seconds,
                    "label": key_detection_result.best_key,
                    "confidence": float(key_detection_result.confidence),
                }
            )

    tessitura_payload: Dict[str, Any] = {}
    if voiced_midi:
        try:
            tessitura_result = analyze_tessitura(
                voiced_midi,
                confidences=frame_confidences if frame_confidences else None,
                uncertainties=frame_uncertainties if frame_uncertainties else None,
                return_pdf=True,
            )
            tessitura_payload = _serialize_tessitura_payload(tessitura_result)
        except Exception as exc:
            warnings.append(f"Tessitura analysis unavailable: {exc}")

    advanced_payload: Dict[str, Any] = {}
    try:
        vibrato = detect_vibrato(
            voiced_f0,
            sample_rate=sample_rate,
            hop_length=STFT_HOP,
        )
        advanced_payload["vibrato"] = {
            "valid": bool(vibrato.valid),
            "rate_hz": _safe_float(vibrato.rate_hz),
            "depth_cents": _safe_float(vibrato.depth_cents),
            "peak_power": _safe_float(vibrato.peak_power),
            "power_ratio": _safe_float(vibrato.power_ratio),
            "start_index": int(vibrato.start_index),
            "n_frames": int(vibrato.n_frames),
        }
    except Exception as exc:
        warnings.append(f"Vibrato analysis unavailable: {exc}")

    try:
        formant_track = estimate_formants_from_audio(
            mono_audio,
            sample_rate=sample_rate,
            hop_length=STFT_HOP,
        )
        advanced_payload["formants"] = _summarize_formants(formant_track)
    except Exception as exc:
        warnings.append(f"Formant analysis unavailable: {exc}")

    try:
        phrase_result = segment_phrases_from_audio(
            mono_audio,
            sample_rate=sample_rate,
            hop_length=STFT_HOP,
        )
        advanced_payload["phrases"] = _summarize_phrases(phrase_result)
    except Exception as exc:
        warnings.append(f"Phrase segmentation unavailable: {exc}")

    analysis_uncertainty = summarize_uncertainty(
        [
            {
                "metadata": {"note_frequencies_hz": voiced_f0},
                "pitch_error_cents": pitch_errors,
            }
        ]
    )
    reference_uncertainty = _build_reference_calibration_uncertainty()
    inferential_statistics = _build_inferential_statistics(
        voiced_f0=voiced_f0,
        voiced_midi=voiced_midi,
        pitch_errors=pitch_errors,
        metadata=metadata,
    )
    calibration_summary = _build_calibration_summary(
        reference_uncertainty,
    )
    evidence_payload = _build_evidence_payload(
        pitch_frames,
        note_events=note_events,
        duration_seconds=duration_seconds,
    )

    metadata_payload: Dict[str, Any] = {
        "sample_rate": sample_rate,
        "hop_length": STFT_HOP,
        "frame_rate": float(sample_rate) / float(max(STFT_HOP, 1)),
        "duration_seconds": duration_seconds,
    }
    if separation_info:
        metadata_payload["vocal_separation"] = separation_info
    if isinstance(metadata, Mapping):
        for key, value in metadata.items():
            if str(key).startswith("_"):
                continue
            metadata_payload[str(key)] = value

    analysis_payload: Dict[str, Any] = {
        "metadata": metadata_payload,
        "summary": {},
        "pitch": {
            "frames": pitch_frames,
            "f0_min": float(np.min(voiced_f0)) if voiced_f0 else None,
            "f0_max": float(np.max(voiced_f0)) if voiced_f0 else None,
        },
        "pitch_frames": pitch_frames,
        "note_events": note_events,
        "notes": {"events": note_events},
        "chords": {"timeline": chord_timeline},
        "keys": {
            "trajectory": key_trajectory,
            "probabilities": key_probabilities,
            "best_key": key_detection_result.best_key if key_detection_result else None,
        },
        "tessitura": tessitura_payload,
        "advanced": advanced_payload,
        "uncertainty": analysis_uncertainty,
        "inferential_statistics": inferential_statistics,
        "calibration": {
            "summary": calibration_summary,
        },
        "diagnostics": {
            "pitch_analysis_methods": pitch_method_diagnostics,
        },
        "evidence": evidence_payload,
    }
    analysis_payload["summary"] = _build_summary(analysis_payload, duration_seconds=duration_seconds)

    export_files: Dict[str, str] = {}
    export_stem = f"{Path(file_path).stem}_{uuid4().hex[:8]}"
    export_json_path = OUTPUT_DIR / f"{export_stem}.json"
    export_csv_path = OUTPUT_DIR / f"{export_stem}.csv"
    export_pdf_path = OUTPUT_DIR / f"{export_stem}.pdf"

    try:
        generate_json_report(analysis_payload, output_path=str(export_json_path))
        export_files["json"] = str(export_json_path)
    except Exception as exc:
        warnings.append(f"JSON export unavailable: {exc}")
        logger.warning("analysis_export_json_failed file_path=%s error=%s", file_path, exc)

    try:
        generate_csv_report(analysis_payload, output_path=str(export_csv_path))
        export_files["csv"] = str(export_csv_path)
    except Exception as exc:
        warnings.append(f"CSV export unavailable: {exc}")
        logger.warning("analysis_export_csv_failed file_path=%s error=%s", file_path, exc)

    try:
        generate_pdf_report(analysis_payload, output_path=str(export_pdf_path))
        export_files["pdf"] = str(export_pdf_path)
    except Exception as exc:
        warnings.append(f"PDF export unavailable: {exc}")
        logger.warning("analysis_export_pdf_failed file_path=%s error=%s", file_path, exc)

    if export_files:
        analysis_payload["files"] = dict(export_files)
        if export_files.get("json"):
            analysis_payload["result_path"] = export_files["json"]

    if warnings:
        analysis_payload["warnings"] = warnings

    response_payload: Dict[str, Any] = {
        "analysis": analysis_payload,
    }
    if export_files:
        response_payload["files"] = dict(export_files)
        if export_files.get("json"):
            response_payload["result_path"] = export_files["json"]

    return response_payload


async def analysis_pipeline(
    file_path: str,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(_run_analysis_pipeline, file_path=file_path, metadata=metadata)


@router.get("/examples")
def list_example_tracks() -> Dict[str, Any]:
    examples = _list_available_example_tracks()
    logger.info("example_gallery.endpoint_response available_examples=%d", len(examples))
    return {"examples": examples}


def _resolve_example_file(filename: str) -> Path:
    """Resolve and validate an example filename to an absolute path within EXAMPLES_DIR."""
    examples_root = EXAMPLES_DIR.resolve()
    if not examples_root.exists():
        raise HTTPException(status_code=404, detail="Examples directory not found.")
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    candidate = (examples_root / filename).resolve()
    try:
        candidate.relative_to(examples_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Example file not found.")
    return candidate


@router.get("/examples/{filename}/thumbnail")
def serve_example_thumbnail(filename: str) -> Any:
    """Extract and return embedded artwork from an example audio file via mutagen.

    Supports FLAC (native PICTURE blocks), Ogg/Opus (VorbisComment METADATA_BLOCK_PICTURE),
    MP3 (ID3 APIC frame), and MP4/M4A (covr atom).
    Returns 404 when no embedded artwork is present.
    """
    import base64
    import struct

    from mutagen.flac import FLAC
    from mutagen.id3 import ID3NoHeaderError
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis

    candidate = _resolve_example_file(filename)
    extension = candidate.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Example file not found.")

    picture_data: Optional[bytes] = None
    picture_mime: str = "image/jpeg"

    try:
        if extension == ".flac":
            audio = FLAC(str(candidate))
            if audio.pictures:
                pic = audio.pictures[0]
                picture_data = pic.data
                picture_mime = pic.mime or "image/jpeg"

        elif extension in (".opus", ".ogg"):
            audio = OggOpus(str(candidate)) if extension == ".opus" else OggVorbis(str(candidate))
            raw_list = audio.get("metadata_block_picture", [])
            if raw_list:
                raw = base64.b64decode(raw_list[0])
                offset = 0
                offset += 4  # picture type
                mime_len = struct.unpack_from(">I", raw, offset)[0]; offset += 4
                mime_bytes = raw[offset: offset + mime_len]; offset += mime_len
                desc_len = struct.unpack_from(">I", raw, offset)[0]; offset += 4
                offset += desc_len  # description
                offset += 16  # width, height, color depth, colors used
                data_len = struct.unpack_from(">I", raw, offset)[0]; offset += 4
                picture_data = raw[offset: offset + data_len]
                picture_mime = mime_bytes.decode("utf-8", errors="replace") or "image/jpeg"

        elif extension == ".mp3":
            try:
                from mutagen.id3 import ID3, APIC
                tags = ID3(str(candidate))
                apic_keys = [k for k in tags.keys() if k.startswith("APIC")]
                if apic_keys:
                    apic = tags[apic_keys[0]]
                    picture_data = apic.data
                    picture_mime = apic.mime or "image/jpeg"
            except ID3NoHeaderError:
                pass

        elif extension in (".m4a", ".mp4", ".aac"):
            audio = MP4(str(candidate))
            covr = audio.tags.get("covr") if audio.tags else None
            if covr:
                img = covr[0]
                picture_data = bytes(img)
                picture_mime = (
                    "image/png"
                    if getattr(img, "imageformat", None) == MP4Cover.FORMAT_PNG
                    else "image/jpeg"
                )

    except Exception:
        pass  # Mutagen parse failure — no artwork available.

    if not picture_data:
        raise HTTPException(status_code=404, detail="No embedded artwork found.")

    logger.info(
        "example_gallery.serve_thumbnail filename=%s mime=%s size=%d",
        filename,
        picture_mime,
        len(picture_data),
    )
    return Response(content=picture_data, media_type=picture_mime)


@router.get("/examples/{filename}")
def serve_example_file(filename: str) -> Any:
    """Serve an example audio file or image sidecar from EXAMPLES_DIR."""
    candidate = _resolve_example_file(filename)
    extension = candidate.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS and extension not in EXAMPLE_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Example file not found.")

    if extension in EXAMPLE_IMAGE_EXTENSIONS:
        media_type, _ = mimetypes.guess_type(candidate.name)
        media_type = media_type or "application/octet-stream"
    elif extension in EXAMPLE_CONTENT_TYPE_OVERRIDES:
        media_type = EXAMPLE_CONTENT_TYPE_OVERRIDES[extension]
    else:
        media_type, _ = mimetypes.guess_type(candidate.name)
        media_type = media_type or "audio/*"

    logger.info(
        "example_gallery.serve_file filename=%s extension=%s media_type=%s",
        filename,
        extension,
        media_type,
    )
    return FileResponse(str(candidate), media_type=media_type, filename=filename)


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
            "audio_type_requested": "analytical",
            "audio_type_detected": "analytical",
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
    logger.info(
        "analysis_status_poll job_id=%s status=%s progress=%s stage=%s",
        job_id,
        job.status,
        job.progress,
        job.stage,
    )
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


# ---------------------------------------------------------------------------
# Reference track management endpoints
# ---------------------------------------------------------------------------


@router.post("/reference/upload")
async def upload_reference_track(
    request: Request,
    audio: UploadFile = File(...),
) -> Dict[str, Any]:
    """Upload an audio file as a reference track.

    Analyzes the file synchronously and caches the result.

    Returns:
        ``{ reference_id, duration_s, key, pitch_frame_count, note_event_count }``
    """
    _rate_limit_check(request)
    file_path = await _save_upload(audio)
    try:
        result = await asyncio.to_thread(
            _run_analysis_pipeline,
            file_path=str(file_path),
            metadata={
                "filename": audio.filename,
                "content_type": audio.content_type,
                "source": "upload",
            },
        )
    except Exception as exc:
        logger.error("reference_upload.pipeline_error filename=%s error=%s", audio.filename, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {_sanitize_error(str(exc))}")
    finally:
        # Clean up the temporary upload file.
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass

    ref_analysis = _ref_cache.build_reference_analysis(
        source="upload",
        source_id=audio.filename or file_path.name,
        pipeline_result=result.get("analysis", {}),
    )
    _ref_cache.store(ref_analysis)

    logger.info(
        "reference_upload.stored reference_id=%s source_id=%s duration_s=%.2f pitch_frames=%d note_events=%d",
        ref_analysis.reference_id,
        ref_analysis.source_id,
        ref_analysis.duration_s,
        len(ref_analysis.pitch_track),
        len(ref_analysis.note_events),
    )

    return {
        "reference_id": ref_analysis.reference_id,
        "duration_s": ref_analysis.duration_s,
        "key": ref_analysis.key,
        "pitch_frame_count": len(ref_analysis.pitch_track),
        "note_event_count": len(ref_analysis.note_events),
    }


@router.post("/reference/from-example/{example_id}")
async def reference_from_example(
    example_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Use a gallery example track as a reference.

    Checks the cache first; analyzes if not already cached.

    Returns:
        ``{ reference_id, duration_s, key, pitch_frame_count, note_event_count, cached: bool }``
    """
    # Check cache by source_id to avoid re-analyzing the same example.
    for cached in _ref_cache.list_all():
        if cached.source == "example" and cached.source_id == example_id:
            logger.info(
                "reference_from_example.cache_hit reference_id=%s example_id=%s",
                cached.reference_id,
                example_id,
            )
            return {
                "reference_id": cached.reference_id,
                "duration_s": cached.duration_s,
                "key": cached.key,
                "pitch_frame_count": len(cached.pitch_track),
                "note_event_count": len(cached.note_events),
                "cached": True,
            }

    example, file_path = _resolve_example_track(example_id)
    try:
        result = await asyncio.to_thread(
            _run_analysis_pipeline,
            file_path=str(file_path),
            metadata={
                "filename": example.get("filename", example_id),
                "content_type": example.get("content_type", "audio/*"),
                "source": "example",
                "example_id": example_id,
            },
        )
    except Exception as exc:
        logger.error(
            "reference_from_example.pipeline_error example_id=%s error=%s", example_id, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Analysis failed: {_sanitize_error(str(exc))}")

    ref_analysis = _ref_cache.build_reference_analysis(
        source="example",
        source_id=example_id,
        pipeline_result=result.get("analysis", {}),
    )
    _ref_cache.store(ref_analysis)

    logger.info(
        "reference_from_example.stored reference_id=%s example_id=%s duration_s=%.2f",
        ref_analysis.reference_id,
        example_id,
        ref_analysis.duration_s,
    )

    return {
        "reference_id": ref_analysis.reference_id,
        "duration_s": ref_analysis.duration_s,
        "key": ref_analysis.key,
        "pitch_frame_count": len(ref_analysis.pitch_track),
        "note_event_count": len(ref_analysis.note_events),
        "cached": False,
    }


@router.get("/reference/{reference_id}")
def get_reference_analysis(reference_id: str) -> Dict[str, Any]:
    """Retrieve the full cached reference analysis for a *reference_id*.

    Returns:
        ``{ reference_id, source, source_id, duration_s, key, pitch_track_summary, note_events,
        tessitura_center_midi, formant_summary }``

    Raises:
        404 if the *reference_id* is not found in the cache.
    """
    ref = _ref_cache.get(reference_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Reference not found.")

    # Summarise pitch track to avoid sending all frames in every call.
    pitch_summary: Dict[str, Any] = {
        "frame_count": len(ref.pitch_track),
        "first_frame": ref.pitch_track[0] if ref.pitch_track else None,
        "last_frame": ref.pitch_track[-1] if ref.pitch_track else None,
    }

    return {
        "reference_id": ref.reference_id,
        "source": ref.source,
        "source_id": ref.source_id,
        "duration_s": ref.duration_s,
        "key": ref.key,
        "pitch_track_summary": pitch_summary,
        "note_events": ref.note_events,
        "tessitura_center_midi": ref.tessitura_center_midi,
        "formant_summary": ref.formant_summary,
        "created_at": ref.created_at.isoformat(),
    }
