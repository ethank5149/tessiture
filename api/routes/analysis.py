# api/routes/analysis.py
"""
Analysis status and results routes.

Endpoints for checking job status and retrieving analysis results.
"""

from typing import Any, Dict

from fastapi import APIRouter, Query

from api import api_router as main_routes

router = APIRouter()


@router.get("/status/{job_id}")
def get_status(job_id: str) -> Dict[str, Any]:
    """Get the current status of an analysis job.

    Args:
        job_id: The unique identifier of the job.

    Returns:
        Job status information including state, progress, and timestamps.
    """
    return main_routes._get_status(job_id)


@router.get("/results/{job_id}")
def get_results(
    job_id: str,
    format: str = Query("json", pattern="^(json|json_report|csv|pdf)$"),
) -> Any:
    """Get the results of a completed analysis job.

    Args:
        job_id: The unique identifier of the job.
        format: Output format - json, json_report, csv, or pdf.

    Returns:
        Analysis results in the requested format.
    """
    return main_routes._get_results(job_id, format)
