# api/routes/upload.py
"""
File upload and job creation routes.

Endpoints for uploading audio files and creating analysis jobs.
"""

from typing import Any, Dict

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

from api import job_manager
from api import api_router as main_routes

router = APIRouter()


@router.post("/analyze/example")
async def analyze_example_audio(
    request: Request,
    example_id: str = Query(..., min_length=1),
) -> Dict[str, Any]:
    """Start an analysis job for a gallery example track.

    Returns:
        ``{ job_id, status_url, results_url }``
    """
    main_routes._rate_limit_check(request)
    example, file_path = main_routes._resolve_example_track(example_id)
    job_id = job_manager.create_job(
        str(file_path),
        main_routes.analysis_pipeline,
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
    main_routes._job_file_paths[job_id] = str(file_path)
    return {
        "job_id": job_id,
        "status_url": f"/status/{job_id}",
        "results_url": f"/results/{job_id}",
    }


@router.post("/analyze")
async def analyze_audio(
    request: Request,
    audio: UploadFile = File(...),
    audio_type: str = Form("isolated"),
    force_vocal_separation: bool = Form(false),
) -> Dict[str, Any]:
    """Upload and analyse an audio file.

    Returns:
        ``{ job_id, status_url, results_url }``
    """
    main_routes._rate_limit_check(request)
    file_path = await main_routes._save_upload(audio)
    job_id = job_manager.create_job(
        str(file_path),
        main_routes.analysis_pipeline,
        metadata={
            "filename": audio.filename,
            "content_type": audio.content_type,
            "source": "upload",
            "audio_type": audio_type,
            "force_vocal_separation": force_vocal_separation,
        },
    )
    main_routes._job_file_paths[job_id] = str(file_path)
    return {
        "job_id": job_id,
        "status_url": f"/status/{job_id}",
        "results_url": f"/results/{job_id}",
    }
