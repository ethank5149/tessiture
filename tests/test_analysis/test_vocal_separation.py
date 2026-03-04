"""Unit tests for analysis.dsp.vocal_separation module."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from analysis.dsp.vocal_separation import (
    cache_key,
    is_available,
    load_cached_stem,
    save_stem_to_cache,
)


# ---------------------------------------------------------------------------
# is_available()
# ---------------------------------------------------------------------------

def test_is_available_returns_bool():
    result = is_available()
    assert isinstance(result, bool)


def test_is_available_false_when_demucs_missing():
    """Simulate demucs not installed."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in ("demucs", "torch"):
            raise ImportError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        # Re-import the function so the mocked __import__ is used
        import importlib
        import analysis.dsp.vocal_separation as vs_module
        importlib.reload(vs_module)
        assert vs_module.is_available() is False
        # Reload back to normal
        importlib.reload(vs_module)


# ---------------------------------------------------------------------------
# cache_key()
# ---------------------------------------------------------------------------

def test_cache_key_consistent_sha256():
    """Same file content → same SHA-256 hex string."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(b"\x00\x01\x02" * 1000)
        fpath = f.name
    try:
        key1 = cache_key(fpath)
        key2 = cache_key(fpath)
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 hex is 64 chars
        # Confirm it's a valid hex string
        int(key1, 16)
    finally:
        os.unlink(fpath)


def test_cache_key_different_for_different_content():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(b"\x00" * 100)
        fpath_a = f.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(b"\xFF" * 100)
        fpath_b = f.name
    try:
        assert cache_key(fpath_a) != cache_key(fpath_b)
    finally:
        os.unlink(fpath_a)
        os.unlink(fpath_b)


# ---------------------------------------------------------------------------
# save_stem_to_cache() + load_cached_stem() roundtrip
# ---------------------------------------------------------------------------

def _require_soundfile():
    """Skip test if soundfile is not available."""
    try:
        import soundfile  # noqa: F401
    except ImportError:
        pytest.skip("soundfile not available")


def test_cache_roundtrip(tmp_path):
    """Write a stem WAV, read it back, verify shape matches."""
    _require_soundfile()
    audio = np.sin(np.linspace(0, 2 * np.pi, 22050)).astype(np.float32)
    sr = 22050
    key = "a" * 64

    save_stem_to_cache(tmp_path, key, audio, sr)
    result = load_cached_stem(tmp_path, key)

    assert result is not None
    loaded_audio, loaded_sr = result
    assert loaded_sr == sr
    assert loaded_audio.shape == audio.shape
    # Tolerance: PCM_16 introduces some quantisation error
    np.testing.assert_allclose(loaded_audio, audio, atol=1e-3)


def test_save_stem_to_cache_idempotent(tmp_path):
    """Calling save_stem_to_cache twice with same key must not raise."""
    _require_soundfile()
    audio = np.zeros(1000, dtype=np.float32)
    key = "b" * 64

    save_stem_to_cache(tmp_path, key, audio, 16000)
    # Second call should be a no-op (file already exists)
    save_stem_to_cache(tmp_path, key, audio, 16000)


def test_load_cached_stem_returns_none_for_missing(tmp_path):
    """load_cached_stem returns None when cache file doesn't exist."""
    result = load_cached_stem(tmp_path, "nonexistent" * 4)
    assert result is None


# ---------------------------------------------------------------------------
# separate_vocals() — mock-based behaviour when demucs is absent
# ---------------------------------------------------------------------------

def test_separate_vocals_raises_import_error_without_demucs():
    """separate_vocals() raises ImportError when torch cannot be imported."""
    import builtins
    real_import = builtins.__import__

    def mock_import_torch(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("No module named 'torch'")
        return real_import(name, *args, **kwargs)

    from analysis.dsp.vocal_separation import separate_vocals
    audio = np.zeros(1000, dtype=np.float32)

    with patch("builtins.__import__", side_effect=mock_import_torch):
        with pytest.raises(ImportError):
            separate_vocals(audio, 44100)


# ---------------------------------------------------------------------------
# Tests requiring actual demucs — skipped if not installed
# ---------------------------------------------------------------------------

_demucs_available = pytest.mark.skipif(
    not is_available(),
    reason="demucs/torch not installed, skipping model tests",
)


@_demucs_available
def test_separate_vocals_cache_path_integration(tmp_path):
    """Verify that separate_vocals writes to cache on the first call.

    This test requires demucs to be importable but does NOT actually run
    the model; it mocks apply_model to return a zeroed tensor.
    """
    import torch
    import torchaudio  # noqa: F401 — imported inside separate_vocals

    from analysis.dsp.vocal_separation import separate_vocals

    audio = np.random.randn(22050).astype(np.float32)
    sr = 22050

    # Create a minimal mock model
    mock_model = MagicMock()
    mock_model.samplerate = sr
    mock_model.sources = ["drums", "bass", "other", "vocals"]
    mock_model.eval.return_value = mock_model
    mock_model.to.return_value = mock_model
    params_iter = iter([torch.nn.Parameter(torch.zeros(1))])
    mock_model.parameters.return_value = params_iter

    # Fake sources output: (batch=1, stems=4, channels=2, samples)
    fake_sources = torch.zeros(1, 4, 2, sr)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        import soundfile as sf
        sf.write(f.name, audio, sr)
        fpath = f.name

    try:
        with (
            patch("analysis.dsp.vocal_separation._load_model", return_value=(mock_model, "htdemucs")),
            patch("analysis.dsp.vocal_separation.apply_model", return_value=fake_sources),
            patch("torch.cuda.is_available", return_value=False),
        ):
            result = separate_vocals(
                audio, sr,
                file_path=fpath,
                cache_dir=tmp_path,
            )

        assert result.cache_hit is False
        assert result.model_name == "htdemucs"
        assert result.vocals.ndim == 1

        # Second call should hit cache
        with (
            patch("analysis.dsp.vocal_separation._load_model", return_value=(mock_model, "htdemucs")),
            patch("analysis.dsp.vocal_separation.apply_model", return_value=fake_sources),
        ):
            result2 = separate_vocals(
                audio, sr,
                file_path=fpath,
                cache_dir=tmp_path,
            )

        assert result2.cache_hit is True
    finally:
        os.unlink(fpath)
