"""Logging configuration for Tessiture application.

This module provides:
- Global application logger with console and file handlers
- Job-level logger factory for per-job logging
- Cleanup utilities for old job log directories
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

# Configuration defaults
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIR = "/tmp/tessiture_logs"
DEFAULT_JOBS_DIR = "/tmp/tessiture_jobs"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 3
DEFAULT_LOG_CLEANUP_DAYS = 7

# Environment variable names
ENV_LOG_LEVEL = "TESSITURE_LOG_LEVEL"
ENV_LOG_DIR = "TESSITURE_LOG_DIR"
ENV_JOBS_DIR = "TESSITURE_JOBS_DIR"
ENV_LOG_CLEANUP_DAYS = "TESSITURE_LOG_CLEANUP_DAYS"

# Global state
_loggers: Dict[str, logging.Logger] = {}
_job_loggers: Dict[str, logging.Logger] = {}
_log_dir: Optional[Path] = None
_jobs_dir: Optional[Path] = None


def _get_log_dir() -> Path:
    """Get the log directory path from environment or default."""
    global _log_dir
    if _log_dir is None:
        log_dir_str = os.getenv(ENV_LOG_DIR, DEFAULT_LOG_DIR)
        _log_dir = Path(log_dir_str)
    return _log_dir


def _get_jobs_dir() -> Path:
    """Get the jobs directory path from environment or default."""
    global _jobs_dir
    if _jobs_dir is None:
        jobs_dir_str = os.getenv(ENV_JOBS_DIR, DEFAULT_JOBS_DIR)
        _jobs_dir = Path(jobs_dir_str)
    return _jobs_dir


def _get_log_level() -> int:
    """Get the log level from environment or default."""
    level_str = os.getenv(ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL).upper()
    return getattr(logging, level_str, logging.INFO)


def init_logging() -> None:
    """Initialize the global application logger with console and file handlers.
    
    This function sets up:
    - Console handler (INFO level)
    - File handler with rotation (DEBUG level)
    - Proper formatting
    """
    log_dir = _get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels, filter at handlers
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler - INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler - DEBUG and above with rotation
    log_file = log_dir / "tessiture.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Log initialization message
    root_logger.info(
        "Logging initialized: level=%s, log_dir=%s",
        os.getenv(ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL),
        str(log_dir)
    )


def get_logger(name: str) -> logging.Logger:
    """Get a named logger for the application.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Configured logger instance
    """
    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)
    return _loggers[name]


def get_job_logger(job_id: str) -> logging.Logger:
    """Get a logger specific to a job.
    
    Creates a logger with four separate log files per job:
    - debug.log - DEBUG level messages
    - info.log - INFO level messages
    - warning.log - WARNING level messages
    - error.log - ERROR level messages
    
    Args:
        job_id: The unique job identifier (UUID)
    
    Returns:
        Logger instance for the job
    """
    if job_id in _job_loggers:
        return _job_loggers[job_id]
    
    jobs_dir = _get_jobs_dir()
    job_log_dir = jobs_dir / job_id / "logs"
    job_log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create job-specific logger
    job_logger = logging.getLogger(f"job.{job_id}")
    job_logger.setLevel(logging.DEBUG)
    job_logger.propagate = False
    
    # Remove existing handlers if any
    for handler in job_logger.handlers[:]:
        job_logger.removeHandler(handler)
    
    # Custom format with job_id
    job_format = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(job_id)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Add job_id to record factory for custom format
    old_factory = logging.getLogRecordFactory()
    
    def job_record_factory(*args, job_id=job_id, **kwargs):
        record = old_factory(*args, **kwargs)
        record.job_id = job_id
        return record
    
    logging.setLogRecordFactory(job_record_factory)
    
    # DEBUG handler - writes to debug.log
    debug_handler = logging.FileHandler(
        job_log_dir / "debug.log",
        encoding="utf-8"
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.addFilter(_LevelFilter(logging.DEBUG))
    debug_handler.setFormatter(job_format)
    job_logger.addHandler(debug_handler)
    
    # INFO handler - writes to info.log
    info_handler = logging.FileHandler(
        job_log_dir / "info.log",
        encoding="utf-8"
    )
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(_LevelFilter(logging.INFO))
    info_handler.setFormatter(job_format)
    job_logger.addHandler(info_handler)
    
    # WARNING handler - writes to warning.log
    warning_handler = logging.FileHandler(
        job_log_dir / "warning.log",
        encoding="utf-8"
    )
    warning_handler.setLevel(logging.WARNING)
    warning_handler.addFilter(_LevelFilter(logging.WARNING))
    warning_handler.setFormatter(job_format)
    job_logger.addHandler(warning_handler)
    
    # ERROR handler - writes to error.log
    error_handler = logging.FileHandler(
        job_log_dir / "error.log",
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(_LevelFilter(logging.ERROR))
    error_handler.setFormatter(job_format)
    job_logger.addHandler(error_handler)
    
    _job_loggers[job_id] = job_logger
    return job_logger


def get_job_log_dir(job_id: str) -> Path:
    """Get the log directory path for a specific job.
    
    Args:
        job_id: The unique job identifier (UUID)
    
    Returns:
        Path to the job's log directory
    """
    jobs_dir = _get_jobs_dir()
    return jobs_dir / job_id / "logs"


class _LevelFilter(logging.Filter):
    """Filter that only passes records at a specific level."""
    
    def __init__(self, level: int):
        super().__init__()
        self.level = level
    
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self.level


def cleanup_old_job_logs(days: Optional[int] = None) -> int:
    """Clean up old job log directories.
    
    Args:
        days: Number of days to keep logs (default from TESSITURE_LOG_CLEANUP_DAYS or 7)
    
    Returns:
        Number of directories cleaned up
    """
    if days is None:
        days = int(os.getenv(ENV_LOG_CLEANUP_DAYS, DEFAULT_LOG_CLEANUP_DAYS))
    
    jobs_dir = _get_jobs_dir()
    if not jobs_dir.exists():
        return 0
    
    cutoff = datetime.now() - timedelta(days=days)
    cleaned = 0
    
    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        
        # Check modification time
        mtime = datetime.fromtimestamp(job_dir.stat().st_mtime)
        if mtime < cutoff:
            try:
                shutil.rmtree(job_dir)
                cleaned += 1
            except OSError:
                pass  # Skip on error
    
    return cleaned


def get_log_dir() -> Path:
    """Get the configured log directory path.
    
    Returns:
        Path to the global log directory
    """
    return _get_log_dir()


def get_jobs_dir() -> Path:
    """Get the configured jobs directory path.
    
    Returns:
        Path to the jobs directory
    """
    return _get_jobs_dir()
