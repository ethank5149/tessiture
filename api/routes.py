from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Set
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from api import job_manager

router = APIRouter()

# Upload validation configuration (comma-separated env vars)
UPLOAD_DIR = Path(os.getenv("TESSITURE_UPLOAD_DIR", "/tmp/tessiture_uploads"))
DEFAULT_UPLOAD_EXTENSIONS = ".wav,.mp3,.flac,.m4a"
DEFAULT_UPLOAD_MIME_TYPES = "audio/wav,audio/x-wav,audio/mpeg,audio/flac,audio/x-flac,audio/mp4"
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

# Rate limiting placeholder (token bucket per client IP).
RATE_LIMIT_CAPACITY = int(os.getenv("TESSITURE_RATE_LIMIT_CAPACITY", "10"))
RATE_LIMIT_REFILL_PER_SEC = float(os.getenv("TESSITURE_RATE_LIMIT_REFILL_PER_SEC", "0.5"))
_RATE_LIMIT_BUCKETS: Dict[str, Dict[str, float]] = {}


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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


async def analysis_stub(
    file_path: str,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Stub analysis function for Phase 7.1 API wiring only."""
    return {
        "message": "Analysis stub: no processing performed.",
        "input_path": file_path,
        "metadata": dict(metadata) if metadata else None,
        "files": {},
    }


@router.post("/analyze")
async def analyze_audio(request: Request, audio: UploadFile = File(...)) -> Dict[str, Any]:
    _rate_limit_check(request)
    file_path = await _save_upload(audio)
    job_id = job_manager.create_job(
        str(file_path),
        analysis_stub,
        metadata={"filename": audio.filename, "content_type": audio.content_type},
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
