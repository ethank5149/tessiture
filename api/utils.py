"""General utility functions for the Tessiture API.

This module contains helper functions for file handling, validation,
serialization, and other common operations.
"""

from __future__ import annotations

import logging
import mimetypes
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set
from uuid import uuid4

import numpy as np
from fastapi import File, HTTPException, Query, Request, UploadFile

from api import config

logger = logging.getLogger(__name__)

# Rate limit buckets storage
_RATE_LIMIT_BUCKETS: Dict[str, Dict[str, float]] = {}


def _safe_float(value: Any) -> Optional[float]:
    """Convert a value to a finite float, or return None if not possible."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _as_finite_array(values: Sequence[Any]) -> np.ndarray:
    """Convert a sequence of values to a finite numpy array."""
    numeric: List[float] = []
    for value in values:
        number = _safe_float(value)
        if number is None:
            continue
        numeric.append(float(number))
    return np.asarray(numeric, dtype=float)


def _ensure_upload_dir() -> None:
    """Ensure the upload directory exists."""
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_output_dir() -> None:
    """Ensure the output directory exists."""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def _save_upload(upload: UploadFile) -> Path:
    """Save an uploaded file to the upload directory.
    
    Args:
        upload: The uploaded file to save.
        
    Returns:
        Path to the saved file.
        
    Raises:
        HTTPException: If the upload exceeds the maximum size or is invalid.
    """
    _ensure_upload_dir()
    suffix = _validate_upload(upload)
    file_path = config.UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    total_bytes = 0
    try:
        with file_path.open("wb") as buffer:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > config.MAX_UPLOAD_BYTES:
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
    """Validate an uploaded file's extension and MIME type.
    
    Args:
        upload: The uploaded file to validate.
        
    Returns:
        The file extension if valid.
        
    Raises:
        HTTPException: If the file is invalid.
    """
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Audio filename is required.")
    suffix = Path(upload.filename).suffix.lower()
    if not suffix or suffix not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported audio file extension.")
    content_type = (upload.content_type or "").lower()
    if content_type not in config.ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio MIME type.")
    return suffix


def _rate_limit_check(request: Request) -> None:
    """Check if the request exceeds rate limits.
    
    Args:
        request: The incoming request.
        
    Raises:
        HTTPException: If rate limit is exceeded.
    """
    if config.RATE_LIMIT_CAPACITY <= 0 or config.RATE_LIMIT_REFILL_PER_SEC <= 0:
        return
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _RATE_LIMIT_BUCKETS.get(client_ip)
    if bucket is None:
        _RATE_LIMIT_BUCKETS[client_ip] = {"tokens": config.RATE_LIMIT_CAPACITY - 1, "last": now}
        return
    tokens = min(
        config.RATE_LIMIT_CAPACITY,
        bucket["tokens"] + (now - bucket["last"]) * config.RATE_LIMIT_REFILL_PER_SEC,
    )
    if tokens < 1:
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    bucket["tokens"] = tokens - 1
    bucket["last"] = now


def _serialize_status(job: Any) -> Dict[str, Any]:
    """Serialize a job status to a dictionary.
    
    Args:
        job: The job status object.
        
    Returns:
        Serialized job status dictionary.
    """
    from api import job_manager
    
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
    """Sanitize an error message for user display.
    
    Args:
        error: The raw error message.
        
    Returns:
        Sanitized error message.
    """
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
    """Extract the result file path from an analysis result.
    
    Args:
        result: The analysis result dictionary.
        fmt: The format (e.g., 'json', 'csv', 'pdf').
        
    Returns:
        The result file path, or None if not found.
    """
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


def _is_voiced_frame(frame: Mapping[str, Any]) -> bool:
    """Return True only for frames that pass frequency-range and confidence checks.

    Mirrors the logic in :func:`analysis.pitch.estimator.compute_voicing_mask`
    so that voiced_f0 collections in the pipeline stay free of artifact extremes.
    
    Args:
        frame: A frame dictionary containing f0_hz, f0, confidence, or salience.
        
    Returns:
        True if the frame is considered voiced, False otherwise.
    """
    f0 = _safe_float(frame.get("f0_hz") or frame.get("f0"))
    if f0 is None or not (config._VOICED_MIN_HZ <= f0 <= config._VOICED_MAX_HZ):
        return False
    confidence = _safe_float(frame.get("confidence") or frame.get("salience"))
    return confidence is not None and confidence >= config._VOICED_MIN_SALIENCE


def _build_example_payload(example: Mapping[str, Any], file_path: Path) -> Dict[str, Any]:
    """Build an example payload dictionary.
    
    Args:
        example: The example metadata.
        file_path: Path to the example file.
        
    Returns:
        Formatted example payload.
    """
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
    """Convert a file path to a slugified example ID.
    
    Args:
        file_path: Path to the example file.
        
    Returns:
        Slugified example ID.
    """
    base = re.sub(r"[^a-z0-9]+", "-", file_path.stem.lower()).strip("-")
    return base or "example"


def _guess_example_content_type(file_path: Path) -> str:
    """Guess the content type of an example file.
    
    Args:
        file_path: Path to the example file.
        
    Returns:
        Guessed content type.
    """
    extension = file_path.suffix.lower()
    if extension in config.EXAMPLE_CONTENT_TYPE_OVERRIDES:
        return config.EXAMPLE_CONTENT_TYPE_OVERRIDES[extension]
    guessed, _ = mimetypes.guess_type(file_path.name)
    return guessed or "audio/*"


def _parse_example_stem(stem: str) -> Dict[str, Optional[str]]:
    """Parse artist, optional album, and title from an example filename stem.

    Filename schema (delimiter is ' - '):
        Title                        → title only
        Artist - Title               → artist + title
        Artist - Album - Title       → artist + album + title
        Artist - A - B - Title       → artist + album('A - B') + title
        
    Args:
        stem: The filename stem to parse.
        
    Returns:
        Dictionary with artist, album, and title.
    """
    parts = stem.split(config._FILENAME_DELIMITER)
    if len(parts) == 1:
        return {"artist": None, "album": None, "title": parts[0].strip()}
    if len(parts) == 2:
        return {"artist": parts[0].strip(), "album": None, "title": parts[1].strip()}
    return {
        "artist": parts[0].strip(),
        "album": config._FILENAME_DELIMITER.join(parts[1:-1]).strip(),
        "title": parts[-1].strip(),
    }


def _discover_example_tracks() -> List[tuple[Dict[str, Any], Path]]:
    """Discover all available example tracks in the examples directory.
    
    Returns:
        List of tuples containing example metadata and file path.
    """
    discovered: List[tuple[Dict[str, Any], Path]] = []
    used_ids: Set[str] = set()
    examples_root = config.EXAMPLES_DIR.resolve()

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
        if extension and extension not in config.ALLOWED_EXTENSIONS:
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
    """List all available example tracks.
    
    Returns:
        List of example track metadata.
    """
    return [example for example, _ in _discover_example_tracks()]


def _resolve_example_track(example_id: str) -> tuple[Dict[str, Any], Path]:
    """Resolve an example track by its ID.
    
    Args:
        example_id: The example track ID.
        
    Returns:
        Tuple of example metadata and file path.
        
    Raises:
        HTTPException: If the example is not found.
    """
    normalized_id = (example_id or "").strip()
    if not normalized_id:
        raise HTTPException(status_code=400, detail="Example ID is required.")

    logger.info("example_gallery.resolve_start requested_id=%s", normalized_id)

    discovered = _discover_example_tracks()

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
        "example_gallery.resolve_not_found requested_id=%s",
        normalized_id,
    )
    raise HTTPException(status_code=404, detail="Example track not found.")


def get_job_file_paths() -> Dict[str, str]:
    """Get the job file paths registry.
    
    Returns:
        Dictionary mapping job IDs to file paths.
    """
    return config._job_file_paths


def register_job_file_path(job_id: str, file_path: str) -> None:
    """Register a file path for a job.
    
    Args:
        job_id: The job ID.
        file_path: The file path to register.
    """
    config._job_file_paths[job_id] = file_path


def clear_job_file_path(job_id: str) -> None:
    """Clear a job's file path from the registry.
    
    Args:
        job_id: The job ID.
    """
    config._job_file_paths.pop(job_id, None)
