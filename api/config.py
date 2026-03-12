"""Configuration constants and defaults for the Tessiture API.

This module centralizes all configuration values that were previously
defined at the top of api_router.py.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Set

# Upload and output configuration
UPLOAD_DIR = Path(os.getenv("TESSITURE_UPLOAD_DIR", "/tmp/tessiture_uploads"))
OUTPUT_DIR = Path(os.getenv("TESSITURE_OUTPUT_DIR", "/tmp/tessiture_outputs"))
EXAMPLES_DIR = Path(
    os.getenv(
        "TESSITURE_EXAMPLES_DIR",
        str(Path(__file__).resolve().parents[1] / "examples" / "tracks"),
    )
)

# Default upload extensions and MIME types
DEFAULT_UPLOAD_EXTENSIONS = ".wav,.mp3,.flac,.m4a,.opus"
DEFAULT_UPLOAD_MIME_TYPES = (
    "audio/wav,audio/x-wav,audio/mpeg,audio/flac,audio/x-flac,audio/mp4,"
    "audio/opus,audio/x-opus,audio/ogg,application/ogg"
)

# Allowed extensions and MIME types (computed from environment or defaults)
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

# Analysis defaults
TARGET_SAMPLE_RATE = int(os.getenv("TESSITURE_TARGET_SAMPLE_RATE", "44100"))
STFT_NFFT = int(os.getenv("TESSITURE_STFT_NFFT", "4096"))
STFT_HOP = int(os.getenv("TESSITURE_STFT_HOP", "512"))
NOTE_EVENT_MIN_CONFIDENCE = float(os.getenv("TESSITURE_NOTE_EVENT_MIN_CONFIDENCE", "0.15"))
NOTE_EVENT_MIN_FRAMES = int(os.getenv("TESSITURE_NOTE_EVENT_MIN_FRAMES", "3"))
NOTE_EVENT_SPLIT_HYSTERESIS_MIDI = float(os.getenv("TESSITURE_NOTE_EVENT_SPLIT_HYSTERESIS_MIDI", "0.45"))
BOOTSTRAP_SAMPLES = int(os.getenv("TESSITURE_BOOTSTRAP_SAMPLES", "1000"))
BOOTSTRAP_CONFIDENCE_LEVEL = float(os.getenv("TESSITURE_BOOTSTRAP_CONFIDENCE_LEVEL", "0.95"))
REFERENCE_CALIBRATION_SAMPLE_COUNT = int(os.getenv("TESSITURE_REFERENCE_CALIBRATION_SAMPLES", "24"))
REFERENCE_CALIBRATION_SEED = int(os.getenv("TESSITURE_REFERENCE_CALIBRATION_SEED", "20260303"))
DEFAULT_INFERENTIAL_PRESET = os.getenv("TESSITURE_INFERENTIAL_PRESET", "casual").strip().lower()

# Inferential null presets
INFERENTIAL_NULL_PRESETS: Dict[str, Dict[str, float]] = {
    "casual": {
        "f0_mean_hz": 196.0,
        "f0_min_hz": 130.81,
        "f0_max_hz": 440.0,
        "tessitura_center_midi": 57.0,
        "pitch_error_mean_cents": 0.0,
    },
    "intermediate": {
        "f0_mean_hz": 220.0,
        "f0_min_hz": 130.81,
        "f0_max_hz": 523.25,
        "tessitura_center_midi": 60.0,
        "pitch_error_mean_cents": 0.0,
    },
    "vocalist": {
        "f0_mean_hz": 246.94,
        "f0_min_hz": 146.83,
        "f0_max_hz": 659.25,
        "tessitura_center_midi": 64.0,
        "pitch_error_mean_cents": 0.0,
    },
}

# Rate limiting settings (token bucket per client IP)
RATE_LIMIT_CAPACITY = int(os.getenv("TESSITURE_RATE_LIMIT_CAPACITY", "10"))
RATE_LIMIT_REFILL_PER_SEC = float(os.getenv("TESSITURE_RATE_LIMIT_REFILL_PER_SEC", "0.5"))

# Note names for pitch conversion
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Example content type overrides and image extensions
EXAMPLE_CONTENT_TYPE_OVERRIDES: Dict[str, str] = {
    ".opus": "audio/opus",
    ".m4a": "audio/mp4",
}
EXAMPLE_IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp"}

# Voiced-frame filter thresholds — aligned with compute_voicing_mask defaults
_VOICED_MIN_HZ: float = float(os.getenv("TESSITURE_VOICED_MIN_HZ", "80.0"))
_VOICED_MAX_HZ: float = float(os.getenv("TESSITURE_VOICED_MAX_HZ", "1200.0"))
_VOICED_MIN_SALIENCE: float = float(os.getenv("TESSITURE_VOICED_MIN_SALIENCE", "0.3"))

# Vocal separation configuration
_VOCAL_SEPARATION_MODE: str = os.getenv("TESSITURE_VOCAL_SEPARATION", "auto").lower()
_STEM_CACHE_DIR: Path | None = (
    Path(os.getenv("TESSITURE_STEM_CACHE_DIR", "/data/stem_cache"))
    if os.getenv("TESSITURE_STEM_CACHE_DIR") or _VOCAL_SEPARATION_MODE != "off"
    else None
)

# Spectrogram frequency display bounds (Hz)
_SPECT_FREQ_MIN_HZ: float = 80.0
_SPECT_FREQ_MAX_HZ: float = 8000.0

# Volatile in-process file-path registry
# Populated by the analyze endpoints at job-creation time so that
# /spectrogram/{job_id} can find the source file without re-loading
# the full result. Falls back to metadata._original_file_path stored
# in the analysis result when the dict is empty after a server restart.
_job_file_paths: Dict[str, str] = {}

# Filename delimiter for parsing example stems
_FILENAME_DELIMITER = " - "
