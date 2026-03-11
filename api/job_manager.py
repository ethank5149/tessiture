"""In-memory async job manager for analysis tasks."""
from __future__ import annotations

import asyncio
import inspect
import logging
import traceback
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from api import logging_config

JobState = str
AnalysisResult = Dict[str, Any]
AnalysisFn = Callable[[str, Optional[Mapping[str, Any]]], Awaitable[AnalysisResult] | AnalysisResult]
logger = logging.getLogger(__name__)
_PROGRESS_CALLBACK_KEY = "_progress_callback"


@dataclass
class JobStatus:
    job_id: str
    status: JobState
    progress: int
    created_at: datetime
    updated_at: datetime
    stage: Optional[str] = None
    message: Optional[str] = None
    result_path: Optional[str] = None
    result: Optional[AnalysisResult] = None
    error: Optional[str] = None


_jobs: Dict[str, JobStatus] = {}
_tasks: Dict[str, asyncio.Task[None]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_progress(value: Any) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def _set_status(job_id: str, **updates: Any) -> None:
    job = _jobs[job_id]
    if "progress" in updates:
        updates["progress"] = _coerce_progress(updates["progress"])
    for key, value in updates.items():
        setattr(job, key, value)
    job.updated_at = _now()
    
    # Log progress updates to job logger
    job_logger = logging_config.get_job_logger(job_id)
    progress = updates.get("progress", job.progress)
    stage = updates.get("stage", job.stage)
    message = updates.get("message", job.message)
    job_logger.debug(
        "Progress update: progress=%d, stage=%s, message=%s",
        progress,
        stage,
        message
    )


def _build_progress_callback(job_id: str) -> Callable[[int, Optional[str], Optional[str]], None]:
    def _update(progress: int, stage: Optional[str] = None, message: Optional[str] = None) -> None:
        updates: Dict[str, Any] = {"progress": progress}
        if stage is not None:
            updates["stage"] = stage
        if message is not None:
            updates["message"] = message
        if _jobs[job_id].status == "queued":
            updates["status"] = "processing"
        _set_status(job_id, **updates)

    return _update


async def _run_job(
    job_id: str,
    file_path: str,
    analysis_fn: AnalysisFn,
    metadata: Optional[Mapping[str, Any]],
) -> None:
    job_logger = logging_config.get_job_logger(job_id)
    
    job_logger.info("Job starting: file_path=%s", file_path)
    _set_status(job_id, status="processing", progress=5, stage="starting", message="Analysis job started.")
    try:
        # Add job_id to metadata for analysis pipeline logging
        job_metadata = dict(metadata or {})
        job_metadata["job_id"] = job_id
        job_metadata[_PROGRESS_CALLBACK_KEY] = _build_progress_callback(job_id)
        result_or_coro = analysis_fn(file_path, job_metadata)
        result = await result_or_coro if inspect.isawaitable(result_or_coro) else result_or_coro
        result_path = None
        if isinstance(result, Mapping):
            result_path = result.get("result_path") or result.get("path")
        _set_status(
            job_id,
            status="completed",
            progress=100,
            stage="completed",
            message="Analysis completed.",
            result=dict(result) if isinstance(result, Mapping) else result,
            result_path=result_path,
        )
        job_logger.info("Job completed successfully: job_id=%s, result_path=%s", job_id, result_path)
    except Exception as exc:
        job_logger.exception("Job failed during analysis: job_id=%s, error=%s", job_id, str(exc))
        safe_error = str(exc).strip() or "Analysis failed."
        _set_status(
            job_id,
            status="failed",
            progress=100,
            stage="failed",
            message="Analysis failed.",
            error=safe_error,
        )


def create_job(
    file_path: str,
    analysis_fn: AnalysisFn,
    metadata: Optional[Mapping[str, Any]] = None,
) -> str:
    """Create and enqueue a background analysis job.

    analysis_fn signature: (file_path: str, metadata: Optional[Mapping[str, Any]])
    -> Dict[str, Any] | Awaitable[Dict[str, Any]]
    """
    job_id = str(uuid.uuid4())
    now = _now()
    
    # Create job status
    _jobs[job_id] = JobStatus(
        job_id=job_id,
        status="queued",
        progress=0,
        created_at=now,
        updated_at=now,
        stage="queued",
        message="Job queued.",
    )
    
    # Log job creation
    job_logger = logging_config.get_job_logger(job_id)
    filename = metadata.get("filename") if metadata else None
    source = metadata.get("source") if metadata else None
    job_logger.info(
        "Job created: job_id=%s, filename=%s, source=%s",
        job_id,
        filename,
        source
    )
    
    # Start the job
    loop = asyncio.get_running_loop()
    _tasks[job_id] = loop.create_task(_run_job(job_id, file_path, analysis_fn, metadata))
    return job_id


def get_status(job_id: str) -> Optional[JobStatus]:
    job = _jobs.get(job_id)
    return replace(job) if job else None


def get_result(job_id: str) -> Optional[AnalysisResult]:
    job = _jobs.get(job_id)
    if not job or job.status != "completed":
        return None
    return job.result


def list_jobs() -> List[JobStatus]:
    return [replace(job) for job in _jobs.values()]
