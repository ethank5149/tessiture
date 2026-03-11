# api/routes/reference.py
"""
Reference track management endpoints.

Endpoints for uploading, creating from examples, and retrieving reference track analyses.
"""

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from api import api_router as main_routes
from analysis.comparison import reference_cache as _ref_cache

router = APIRouter()


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
    main_routes._rate_limit_check(request)
    file_path = await main_routes._save_upload(audio)
    try:
        result = await asyncio.to_thread(
            main_routes._run_analysis_pipeline,
            file_path=str(file_path),
            metadata={
                "filename": audio.filename,
                "content_type": audio.content_type,
                "source": "upload",
            },
        )
    except Exception as exc:
        main_routes.logger.error(
            "reference_upload.pipeline_error filename=%s error=%s", audio.filename, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Analysis failed: {main_routes._sanitize_error(str(exc))}")
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

    main_routes.logger.info(
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
            main_routes.logger.info(
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

    example, file_path = main_routes._resolve_example_track(example_id)
    try:
        result = await asyncio.to_thread(
            main_routes._run_analysis_pipeline,
            file_path=str(file_path),
            metadata={
                "filename": example.get("filename", example_id),
                "content_type": example.get("content_type", "audio/*"),
                "source": "example",
                "example_id": example_id,
            },
        )
    except Exception as exc:
        main_routes.logger.error(
            "reference_from_example.pipeline_error example_id=%s error=%s", example_id, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Analysis failed: {main_routes._sanitize_error(str(exc))}")

    ref_analysis = _ref_cache.build_reference_analysis(
        source="example",
        source_id=example_id,
        pipeline_result=result.get("analysis", {}),
    )
    _ref_cache.store(ref_analysis)

    main_routes.logger.info(
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
