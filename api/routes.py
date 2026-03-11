# api/routes.py
"""
Backward compatibility shim.

This module re-exports the router and key functions from api.api_router for backward compatibility.
The actual route implementation is in api/api_router.py and modular route handlers
are in api/routes/.

NOTE: This file exists for backward compatibility. New code should import directly
from api.api_router or from the specific modules in api/routes/.
"""

# Re-export router for backward compatibility
from api.api_router import router

# Re-export key functions and constants for backward compatibility (tests and other modules)
from api.api_router import (
    UPLOAD_DIR,
    OUTPUT_DIR,
    analysis_pipeline,
    _extract_result_path,
    _serialize_status,
    _build_inferential_statistics,
    _build_summary,
    _is_voiced_frame,
    _build_note_events,
    _build_evidence_payload,
    _build_calibration_summary,
    _decode_audio_file,
    _run_analysis_pipeline,
    _parse_example_stem,
    _build_example_payload,
)

__all__ = [
    "router",
    "UPLOAD_DIR",
    "OUTPUT_DIR",
    "analysis_pipeline",
    "_extract_result_path",
    "_serialize_status",
    "_build_inferential_statistics",
    "_build_summary",
    "_is_voiced_frame",
    "_build_note_events",
    "_build_evidence_payload",
    "_build_calibration_summary",
    "_decode_audio_file",
    "_run_analysis_pipeline",
    "_parse_example_stem",
    "_build_example_payload",
]
