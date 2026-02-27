"""In-memory async job manager for analysis tasks."""
from __future__ import annotations

import asyncio
import inspect
import traceback
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

JobState = str
AnalysisResult = Dict[str, Any]
AnalysisFn = Callable[[str, Optional[Mapping[str, Any]]], Awaitable[AnalysisResult] | AnalysisResult]


@dataclass
class JobStatus:
    job_id: str
    status: JobState
    progress: int
    created_at: datetime
    updated_at: datetime
    result_path: Optional[str] = None
    result: Optional[AnalysisResult] = None
    error: Optional[str] = None


_jobs: Dict[str, JobStatus] = {}
_tasks: Dict[str, asyncio.Task[None]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_status(job_id: str, **updates: Any) -> None:
    job = _jobs[job_id]
    for key, value in updates.items():
        setattr(job, key, value)
    job.updated_at = _now()


async def _run_job(
    job_id: str,
    file_path: str,
    analysis_fn: AnalysisFn,
    metadata: Optional[Mapping[str, Any]],
) -> None:
    _set_status(job_id, status="processing", progress=10)
    try:
        result_or_coro = analysis_fn(file_path, metadata)
        result = await result_or_coro if inspect.isawaitable(result_or_coro) else result_or_coro
        result_path = None
        if isinstance(result, Mapping):
            result_path = result.get("result_path") or result.get("path")
        _set_status(
            job_id,
            status="completed",
            progress=100,
            result=dict(result) if isinstance(result, Mapping) else result,
            result_path=result_path,
        )
    except Exception as exc:
        error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _set_status(job_id, status="failed", progress=100, error=error_text)


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
    _jobs[job_id] = JobStatus(
        job_id=job_id,
        status="queued",
        progress=0,
        created_at=now,
        updated_at=now,
    )
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
