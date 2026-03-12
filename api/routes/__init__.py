# api/routes/__init__.py
"""
Modular API route blueprints.

This package contains organized route modules for the Tessiture API.
Each module handles a specific domain of functionality.

NOTE: This module exports the route routers defined in submodules.
The actual route registration happens in api/api_router.py which imports
and includes these routers into the main APIRouter.
"""

# Import modular route blueprints
# These are imported lazily to avoid circular imports
from api.routes import upload
from api.routes import analysis
from api.routes import examples
from api.routes import spectrogram
from api.routes import reference

# Export all route blueprints for easy registration
upload_router = upload.router
analysis_router = analysis.router
examples_router = examples.router
spectrogram_router = spectrogram.router
reference_router = reference.router

# Re-export helper functions and variables from api_router for backward compatibility
# These are used by tests and any external code that imports from api.routes
from api.api_router import (
    # Module-level variables that tests need to access
    UPLOAD_DIR,
    OUTPUT_DIR,
    EXAMPLES_DIR,
    analysis_pipeline,
    _VOCAL_SEPARATION_MODE,
    _vocal_separation_available,
    # Helper functions
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

# Also re-export api_router for tests that need to patch analysis_pipeline
from api import api_router

# Also export the main router for convenience
from api.api_router import router

__all__ = [
    # Route blueprints
    "upload_router",
    "analysis_router",
    "examples_router",
    "spectrogram_router",
    "reference_router",
    # Module-level variables for backward compatibility
    "UPLOAD_DIR",
    "OUTPUT_DIR",
    "EXAMPLES_DIR",
    "analysis_pipeline",
    # Helper functions for backward compatibility
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
    # Main router
    "router",
]
