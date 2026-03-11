# api/routes/spectrogram.py
"""
Spectrogram data endpoints.

Endpoints for retrieving spectrogram visualization data for completed analysis jobs.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from api import job_manager
from api import api_router as main_routes

router = APIRouter()


@router.get("/spectrogram/{job_id}")
def get_spectrogram(job_id: str) -> Dict[str, Any]:
    """Return base64-encoded spectrogram data (mix + optional vocal stem) for a completed job.

    File-path resolution order:
        1. In-process ``_job_file_paths`` dict (populated at job-creation time).
        2. ``result["metadata"]["_original_file_path"]`` stored in the job result
        (survives server restarts because it is serialised with the analysis payload).

    Returns 404 if the job is unknown, 409 if the job is not yet complete,
    and 503 only if the audio file is genuinely unavailable.
    """
    job = job_manager.get_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Job analysis not yet complete.")

    # Resolve file path: in-process dict first, then metadata fallback.
    file_path: Optional[str] = main_routes._job_file_paths.get(job_id)
    vocal_cache_key: Optional[str] = None

    if not file_path or not Path(file_path).is_file():
        result = job_manager.get_result(job_id)
        if result is not None:
            metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
            fallback = metadata.get("_original_file_path") if isinstance(metadata, dict) else None
            if fallback and Path(str(fallback)).is_file():
                file_path = str(fallback)
            separation_info = metadata.get("vocal_separation") if isinstance(metadata, dict) else None
            if isinstance(separation_info, dict) and separation_info.get("applied"):
                try:
                    from analysis.dsp.vocal_separation import cache_key as _voc_cache_key

                    vocal_cache_key = _voc_cache_key(file_path) if file_path else None
                except Exception:
                    pass

    if not file_path or not Path(file_path).is_file():
        raise HTTPException(
            status_code=503,
            detail="Source audio file is no longer available for spectrogram generation.",
        )

    # If we resolved the path from in-process dict, still try to get vocal cache key
    if vocal_cache_key is None and main_routes._job_file_paths.get(job_id):
        result = job_manager.get_result(job_id)
        if result is not None:
            metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
            separation_info = metadata.get("vocal_separation") if isinstance(metadata, dict) else None
            if isinstance(separation_info, dict) and separation_info.get("applied"):
                try:
                    from analysis.dsp.vocal_separation import cache_key as _voc_cache_key

                    vocal_cache_key = _voc_cache_key(file_path)
                except Exception:
                    pass

    main_routes.logger.info(
        "spectrogram_request job_id=%s file_path=%s vocal_cache_key=%s",
        job_id,
        file_path,
        vocal_cache_key[:12] if vocal_cache_key else None,
    )

    return main_routes._build_spectrogram_payload(file_path, vocal_cache_key=vocal_cache_key)
