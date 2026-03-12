from __future__ import annotations

# Re-export configuration from new modules for backward compatibility
from api import config

# Re-export configuration constants for backward compatibility
UPLOAD_DIR = config.UPLOAD_DIR
OUTPUT_DIR = config.OUTPUT_DIR
EXAMPLES_DIR = config.EXAMPLES_DIR
ALLOWED_EXTENSIONS = config.ALLOWED_EXTENSIONS
ALLOWED_MIME_TYPES = config.ALLOWED_MIME_TYPES
MAX_UPLOAD_BYTES = config.MAX_UPLOAD_BYTES
TARGET_SAMPLE_RATE = config.TARGET_SAMPLE_RATE
STFT_NFFT = config.STFT_NFFT
STFT_HOP = config.STFT_HOP
NOTE_EVENT_MIN_CONFIDENCE = config.NOTE_EVENT_MIN_CONFIDENCE
NOTE_EVENT_MIN_FRAMES = config.NOTE_EVENT_MIN_FRAMES
NOTE_EVENT_SPLIT_HYSTERESIS_MIDI = config.NOTE_EVENT_SPLIT_HYSTERESIS_MIDI
BOOTSTRAP_SAMPLES = config.BOOTSTRAP_SAMPLES
BOOTSTRAP_CONFIDENCE_LEVEL = config.BOOTSTRAP_CONFIDENCE_LEVEL
REFERENCE_CALIBRATION_SAMPLE_COUNT = config.REFERENCE_CALIBRATION_SAMPLE_COUNT
REFERENCE_CALIBRATION_SEED = config.REFERENCE_CALIBRATION_SEED
DEFAULT_INFERENTIAL_PRESET = config.DEFAULT_INFERENTIAL_PRESET
INFERENTIAL_NULL_PRESETS = config.INFERENTIAL_NULL_PRESETS
RATE_LIMIT_CAPACITY = config.RATE_LIMIT_CAPACITY
RATE_LIMIT_REFILL_PER_SEC = config.RATE_LIMIT_REFILL_PER_SEC
NOTE_NAMES = config.NOTE_NAMES
EXAMPLE_CONTENT_TYPE_OVERRIDES = config.EXAMPLE_CONTENT_TYPE_OVERRIDES
EXAMPLE_IMAGE_EXTENSIONS = config.EXAMPLE_IMAGE_EXTENSIONS

# Re-export internal config for backward compatibility
_VOICED_MIN_HZ = config._VOICED_MIN_HZ
_VOICED_MAX_HZ = config._VOICED_MAX_HZ
_VOICED_MIN_SALIENCE = config._VOICED_MIN_SALIENCE
_SPECT_FREQ_MIN_HZ = config._SPECT_FREQ_MIN_HZ
_SPECT_FREQ_MAX_HZ = config._SPECT_FREQ_MAX_HZ
_job_file_paths = config._job_file_paths
_FILENAME_DELIMITER = config._FILENAME_DELIMITER
_VOCAL_SEPARATION_MODE = config._VOCAL_SEPARATION_MODE
_STEM_CACHE_DIR = config._STEM_CACHE_DIR

# Import utility functions from new modules
from api.utils import (
    _safe_float,
    _as_finite_array,
    _ensure_upload_dir,
    _ensure_output_dir,
    _save_upload,
    _validate_upload,
    _rate_limit_check,
    _serialize_status,
    _sanitize_error,
    _extract_result_path,
    _is_voiced_frame,
    _build_example_payload,
    _slugify_example_id,
    _guess_example_content_type,
    _parse_example_stem,
    _discover_example_tracks,
    _list_available_example_tracks,
    _resolve_example_track,
    get_job_file_paths,
    register_job_file_path,
    clear_job_file_path,
)

# Import statistical functions from new modules
from api.stats import (
    _build_reference_calibration_uncertainty,
    _resolve_inferential_preset,
    _bootstrap_two_sided_p_value,
    _build_metric_inference,
    _build_inferential_statistics,
    _build_calibration_summary,
)

# Import pitch utilities from new modules
from api.pitch_utils import (
    _midi_to_note_name,
    _hz_to_note_name,
    _unit_supports_pitch_note_names,
    _pitch_value_to_note_name,
    _midi_values_to_note_names,
    _normalize_analysis_diagnostics,
    _extract_pitch_frame_diagnostics,
    _summarize_pitch_method_diagnostics,
    _build_pitch_payload,
    _build_note_events,
)

# Import serialization functions from new modules
from api.serializers import (
    _format_timestamp_label,
    _serialize_tessitura_payload,
    _summarize_formants,
    _summarize_phrases,
    _build_summary,
)

# Import evidence building functions from new modules
from api.evidence import (
    _build_evidence_payload,
    _build_chord_timeline,
)

# Import analysis pipeline functions from new modules
from api.analysis_core import (
    _decode_audio_file,
    _noop_progress_update,
    _resolve_progress_update,
    _run_analysis_pipeline,
    _build_spectrogram_payload,
)

# Original imports
import asyncio
from functools import lru_cache
import logging
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Union
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

from analysis.chords.detector import detect_chord
from analysis.comparison import reference_cache as _ref_cache
from analysis.dsp.vocal_separation import is_available as _vocal_separation_available
from api import job_manager
from api import logging_config
from calibration.reference_generation.lhs_sampler import lhs_sample
from calibration.reference_generation.parameter_ranges import get_default_parameter_ranges

router = APIRouter()
logger = logging.getLogger(__name__)

# Keep _RATE_LIMIT_BUCKETS in local scope for backward compatibility
_RATE_LIMIT_BUCKETS: Dict[str, Dict[str, float]] = {}


# Duplicate utility functions removed - imported from api.utils above
# Functions imported at lines 41-63 are now the source of truth

# Duplicate statistical functions removed - imported from api.stats above
# Functions imported at lines 66-73 are now the source of truth

# Duplicate pitch utility functions removed - imported from api.pitch_utils above
# Functions imported at lines 76-87 are now the source of truth
# _build_note_events reconciled - production implementation now in api/pitch_utils

# Evidence building functions moved to api/evidence.py
# - _build_evidence_payload
# - _build_chord_timeline

# Serialization functions moved to api/serializers.py
# - _serialize_tessitura_payload
# - _summarize_formants
# - _summarize_phrases
# - _build_summary

# Analysis pipeline functions moved to api/analysis_core.py
# - _decode_audio_file
# - _noop_progress_update
# - _resolve_progress_update
# - _run_analysis_pipeline
# - _build_spectrogram_payload

# Public alias exposed at module level so tests can monkeypatch it without
# reaching into the private name.  All analyze endpoints should use this name.
analysis_pipeline = _run_analysis_pipeline


def _get_analysis_pipeline():
    """Get analysis_pipeline, supporting monkeypatching from tests.
    
    This function looks up analysis_pipeline from the routes module,
    allowing tests to monkeypatch routes.analysis_pipeline.
    """
    try:
        from api import routes
        return routes.analysis_pipeline
    except ImportError:
        return analysis_pipeline


# ---------------------------------------------------------------------------
# Helper functions used by modular route handlers
# ---------------------------------------------------------------------------

def _get_status(job_id: str) -> Dict[str, Any]:
    """Get the current status of an analysis job.
    
    Args:
        job_id: The unique identifier of the job.
        
    Returns:
        Job status information including state, progress, and timestamps.
    """
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


def _get_results(job_id: str, format: str = "json") -> Any:
    """Get the results of a completed analysis job.
    
    Args:
        job_id: The unique identifier of the job.
        format: Output format - json, json_report, csv, or pdf.
        
    Returns:
        Analysis results in the requested format.
    """
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


# _list_available_example_tracks already imported from api.utils above
# _build_spectrogram_payload already imported from api.analysis_core above


# ---------------------------------------------------------------------------
# Modular route registration
# This section imports and registers the modular route blueprints from api/routes/
# for backward compatibility and organizational purposes.
# ----------------------------------------------------------------------------
# NOTE: We avoid circular imports by registering routes after all handlers are defined.
# The modular route modules (api/routes/upload.py, etc.) import helper functions
# and constants from this module (api.routes) using `from api import routes as main_routes`.

# Import modular route blueprints
try:
    from api.routes import (
        upload as _upload_module,
        analysis as _analysis_module,
        examples as _examples_module,
        spectrogram as _spectrogram_module,
        reference as _reference_module,
    )

    # Include all modular route routers into the main router
    # This maintains backward compatibility - all endpoints are still accessible
    # via the same `router` object that server.py imports from api.routes
    router.include_router(_upload_module.router, tags=["upload"])
    router.include_router(_analysis_module.router, tags=["analysis"])
    router.include_router(_examples_module.router, tags=["examples"])
    router.include_router(_spectrogram_module.router, tags=["spectrogram"])
    router.include_router(_reference_module.router, tags=["reference"])

except ImportError as e:
    # If modular routes are not available, the monolithic routes defined above remain active
    logger.warning(f"Modular routes not available: {e}")

