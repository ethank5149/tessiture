import asyncio
from datetime import datetime, timezone
import sys
import time
from pathlib import Path
import types

import pytest
from fastapi.testclient import TestClient

from api import job_manager
from api import api_router as main_routes
from api.server import app
from api import utils as _api_utils


def _reset_job_state() -> None:
    for task in list(job_manager._tasks.values()):
        if not task.done():
            task.cancel()
    job_manager._tasks.clear()
    job_manager._jobs.clear()
    # Reset rate-limit buckets so tests don't bleed 429s into each other
    _api_utils._RATE_LIMIT_BUCKETS.clear()


def _wait_for_completion(client: TestClient, job_id: str, timeout_s: float = 3.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        response = client.get(f"/status/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id} to complete")


def test_analyze_status_results_json(tmp_path, monkeypatch) -> None:
    from api import routes
    from api import api_router

    _reset_job_state()
    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"

    async def fake_pipeline(file_path: str, metadata=None):
        routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(file_path).stem
        json_path = routes.OUTPUT_DIR / f"{stem}.json"
        csv_path = routes.OUTPUT_DIR / f"{stem}.csv"
        pdf_path = routes.OUTPUT_DIR / f"{stem}.pdf"
        json_path.write_text("{}", encoding="utf-8")
        csv_path.write_text("time,f0\n0,440\n", encoding="utf-8")
        pdf_path.write_bytes(b"%PDF-1.4\n%EOF\n")
        return {
            "metadata": {
                "filename": (metadata or {}).get("filename"),
            },
            "summary": {
                "duration_seconds": 0.0,
                "f0_min": 440.0,
                "f0_max": 440.0,
                "tessitura_range": [69.0, 69.0],
            },
            "files": {
                "json": str(json_path),
                "csv": str(csv_path),
                "pdf": str(pdf_path),
            },
            "result_path": str(json_path),
        }

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            files={"audio": ("sample.wav", b"RIFFTEST", "audio/wav")},
        )
        assert response.status_code == 200
        payload = response.json()
        job_id = payload.get("job_id")
        assert job_id

        status = _wait_for_completion(client, job_id)
        assert status["status"] == "completed"
        assert status["progress"] == 100
        assert status["stage"] == "completed"
        assert status["message"] == "Analysis completed."
        assert status["detail"] == "Analysis completed."

        result_response = client.get(f"/results/{job_id}?format=json")
        assert result_response.status_code == 200
        result_payload = result_response.json()
        assert "summary" in result_payload
        assert result_payload["summary"]["f0_min"] == 440.0

    _reset_job_state()


def test_status_endpoint_reports_mid_pipeline_progress_fields(tmp_path, monkeypatch) -> None:
    from api import routes
    from api import api_router

    _reset_job_state()
    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"

    async def fake_pipeline(file_path: str, metadata=None):
        progress_callback = (metadata or {}).get("_progress_callback")
        if callable(progress_callback):
            progress_callback(25, "preprocessing", "Preparing audio for analysis.")
            await asyncio.sleep(0.12)
            progress_callback(55, "pitch_extraction", "Extracting pitch contours.")
            await asyncio.sleep(0.12)

        routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(file_path).stem
        json_path = routes.OUTPUT_DIR / f"{stem}.json"
        json_path.write_text("{}", encoding="utf-8")
        return {
            "summary": {"f0_min": 220.0, "f0_max": 220.0},
            "files": {"json": str(json_path)},
            "result_path": str(json_path),
        }

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            files={"audio": ("sample.wav", b"RIFFTEST", "audio/wav")},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        deadline = time.time() + 3.0
        in_flight_status = None
        while time.time() < deadline:
            status_response = client.get(f"/status/{job_id}")
            assert status_response.status_code == 200
            payload = status_response.json()
            if payload.get("stage") in {"preprocessing", "pitch_extraction"}:
                in_flight_status = payload
                break
            if payload.get("status") in {"completed", "failed"}:
                break
            time.sleep(0.03)

        assert in_flight_status is not None
        assert in_flight_status["status"] == "processing"
        assert in_flight_status["progress"] >= 25
        assert in_flight_status["progress"] < 100
        assert isinstance(in_flight_status["message"], str)
        assert in_flight_status["detail"] == in_flight_status["message"]

        final_status = _wait_for_completion(client, job_id)
        assert final_status["status"] == "completed"
        assert final_status["progress"] == 100
        assert final_status["stage"] == "completed"
        assert final_status["message"] == "Analysis completed."

    _reset_job_state()


def test_results_downloads_csv_and_pdf(tmp_path, monkeypatch) -> None:
    from api import routes
    from api import api_router
    from api import api_router

    _reset_job_state()
    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"

    async def fake_pipeline(file_path: str, metadata=None):
        routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(file_path).stem
        csv_path = routes.OUTPUT_DIR / f"{stem}.csv"
        pdf_path = routes.OUTPUT_DIR / f"{stem}.pdf"
        csv_path.write_text("time,f0\n0,220\n", encoding="utf-8")
        pdf_path.write_bytes(b"%PDF-1.4\n%EOF\n")
        return {
            "summary": {"f0_min": 220.0, "f0_max": 220.0},
            "files": {
                "csv": str(csv_path),
                "pdf": str(pdf_path),
            },
            "result_path": str(csv_path),
        }

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            files={"audio": ("sample.wav", b"RIFFTEST", "audio/wav")},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        status = _wait_for_completion(client, job_id)
        assert status["status"] == "completed"

        csv_response = client.get(f"/results/{job_id}?format=csv")
        assert csv_response.status_code == 200
        assert csv_response.headers["content-type"].startswith("text/csv")

        pdf_response = client.get(f"/results/{job_id}?format=pdf")
        assert pdf_response.status_code == 200
        assert pdf_response.headers["content-type"].startswith("application/pdf")

    _reset_job_state()


def test_extract_result_path_json_allows_generic_fallback_only() -> None:
    from api.routes import _extract_result_path

    result = {"result_path": "/tmp/result.json"}

    assert _extract_result_path(result, "json") == "/tmp/result.json"
    assert _extract_result_path(result, "csv") is None
    assert _extract_result_path(result, "pdf") is None


def test_extract_result_path_supports_nested_analysis_payload() -> None:
    from api.routes import _extract_result_path

    result = {
        "analysis": {
            "files": {
                "csv": "/tmp/nested.csv",
                "pdf": "/tmp/nested.pdf",
            },
            "result_path": "/tmp/nested.json",
        }
    }

    assert _extract_result_path(result, "csv") == "/tmp/nested.csv"
    assert _extract_result_path(result, "pdf") == "/tmp/nested.pdf"
    assert _extract_result_path(result, "json") == "/tmp/nested.json"


def test_results_csv_pdf_require_explicit_artifact_paths(tmp_path, monkeypatch) -> None:
    from api import routes

    _reset_job_state()
    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"

    async def fake_pipeline(file_path: str, metadata=None):
        routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(file_path).stem
        generic_json = routes.OUTPUT_DIR / f"{stem}.json"
        generic_json.write_text("{}", encoding="utf-8")
        return {
            "summary": {"f0_min": 220.0, "f0_max": 220.0},
            "result_path": str(generic_json),
        }

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            files={"audio": ("sample.wav", b"RIFFTEST", "audio/wav")},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        status = _wait_for_completion(client, job_id)
        assert status["status"] == "completed"

        json_response = client.get(f"/results/{job_id}?format=json")
        assert json_response.status_code == 200

        csv_response = client.get(f"/results/{job_id}?format=csv")
        assert csv_response.status_code == 404
        assert csv_response.json()["detail"] == "No csv result available."

        pdf_response = client.get(f"/results/{job_id}?format=pdf")
        assert pdf_response.status_code == 404
        assert pdf_response.json()["detail"] == "No pdf result available."

    _reset_job_state()


def test_status_error_payload_is_sanitized_for_failed_jobs(tmp_path, monkeypatch) -> None:
    from api import routes

    _reset_job_state()
    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"

    async def fake_pipeline(_file_path: str, metadata=None):
        raise RuntimeError("intentional failure for client")

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            files={"audio": ("sample.wav", b"RIFFTEST", "audio/wav")},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        status = _wait_for_completion(client, job_id)
        assert status["status"] == "failed"
        assert status["error"] == "intentional failure for client"
        assert "Traceback" not in status["error"]
        assert "\n" not in status["error"]

    _reset_job_state()


def test_serialize_status_sanitizes_traceback_content() -> None:
    from api import routes

    now = datetime.now(timezone.utc)
    job = job_manager.JobStatus(
        job_id="job-1",
        status="failed",
        progress=100,
        created_at=now,
        updated_at=now,
        error=(
            "Traceback (most recent call last):\n"
            "  File \"worker.py\", line 1, in <module>\n"
            "ValueError: unsafe detail"
        ),
    )

    payload = routes._serialize_status(job)

    assert payload["error"] == "unsafe detail"


def test_serialize_status_defaults_stage_when_missing() -> None:
    from api import routes

    now = datetime.now(timezone.utc)
    job = job_manager.JobStatus(
        job_id="job-2",
        status="processing",
        progress=42,
        created_at=now,
        updated_at=now,
        stage=None,
        message=None,
    )

    payload = routes._serialize_status(job)

    assert payload["status"] == "processing"
    assert payload["progress"] == 42
    assert payload["stage"] == "processing"
    assert payload["message"] is None
    assert payload["detail"] is None


def test_build_inferential_statistics_emits_per_metric_ci_and_p_values() -> None:
    from api.routes import _build_inferential_statistics

    payload = _build_inferential_statistics(
        voiced_f0=[220.0, 222.0, 224.0, 226.0, 228.0],
        voiced_midi=[57.0, 58.0, 59.0, 60.0, 61.0],
        pitch_errors=[0.5, -0.25, 0.1, -0.1, 0.0],
        metadata={"inferential_preset": "casual"},
    )

    assert payload["preset"] == "casual"
    assert payload["confidence_level"] == 0.95
    assert payload["bootstrap_samples"] >= 200

    metrics = payload["metrics"]
    assert "f0_mean_hz" in metrics
    assert "f0_min_hz" in metrics
    assert "f0_max_hz" in metrics
    assert "tessitura_center_midi" in metrics
    assert "pitch_error_mean_cents" in metrics

    for metric in metrics.values():
        assert metric["estimate"] is not None
        assert metric["confidence_interval"]["low"] is not None
        assert metric["confidence_interval"]["high"] is not None
        assert metric["n_samples"] > 0
        if metric["p_value"] is not None:
            assert 0.0 <= metric["p_value"] <= 1.0

    midi_metric = metrics["tessitura_center_midi"]
    assert midi_metric["estimate_note"] is not None
    assert midi_metric["confidence_interval"]["low_note"] is not None
    assert midi_metric["confidence_interval"]["high_note"] is not None
    assert midi_metric["null_hypothesis"]["value_note"] is not None

    mean_hz_metric = metrics["f0_mean_hz"]
    min_hz_metric = metrics["f0_min_hz"]
    max_hz_metric = metrics["f0_max_hz"]

    assert mean_hz_metric["estimate_note"] is not None
    assert mean_hz_metric["confidence_interval"]["low_note"] is not None
    assert mean_hz_metric["confidence_interval"]["high_note"] is not None
    assert mean_hz_metric["null_hypothesis"]["value_note"] is not None

    assert min_hz_metric["estimate_note"] is not None
    assert min_hz_metric["confidence_interval"]["low_note"] is not None
    assert min_hz_metric["confidence_interval"]["high_note"] is not None
    assert min_hz_metric["null_hypothesis"]["value_note"] is not None

    assert max_hz_metric["estimate_note"] is not None
    assert max_hz_metric["confidence_interval"]["low_note"] is not None
    assert max_hz_metric["confidence_interval"]["high_note"] is not None
    assert max_hz_metric["null_hypothesis"]["value_note"] is not None

    pitch_error_metric = metrics["pitch_error_mean_cents"]
    assert "estimate_note" not in pitch_error_metric
    assert "low_note" not in pitch_error_metric["confidence_interval"]
    assert "high_note" not in pitch_error_metric["confidence_interval"]
    assert "value_note" not in pitch_error_metric["null_hypothesis"]


def test_build_summary_includes_separate_pitch_and_key_confidence_fields() -> None:
    from api.routes import _build_summary

    result = {
        "pitch": {
            "frames": [
                {"f0_hz": 220.0, "confidence": 0.8},
                {"f0_hz": 230.0, "confidence": 0.6},
            ]
        },
        "tessitura": {
            "metrics": {
                "tessitura_band": [57.0, 61.0],
            }
        },
        "keys": {
            "trajectory": [
                {"label": "A:min", "confidence": 0.4}
            ]
        },
    }

    summary = _build_summary(result, duration_seconds=1.0)

    assert "pitch_confidence" in summary
    assert "key_confidence" in summary
    assert summary["pitch_confidence"] == summary["confidence"]
    assert summary["key_confidence"] == 0.4
    assert summary["f0_min_note"] == "A3"
    assert summary["f0_max_note"] == "A#3"
    assert summary["tessitura_range_notes"] == ["A3", "C#4"]


def test_build_summary_excludes_out_of_range_and_low_confidence_artifacts() -> None:
    from api.routes import _build_summary

    result = {
        "pitch": {
            "frames": [
                {"f0_hz": 220.0, "confidence": 0.8},   # valid voiced frame
                {"f0_hz": 70.0, "confidence": 0.95},   # artifact: below voiced min Hz
                {"f0_hz": 1500.0, "confidence": 0.95}, # artifact: above voiced max Hz
                {"f0_hz": 330.0, "confidence": 0.2},   # low confidence, should be unvoiced
                {"f0_hz": 440.0, "confidence": 0.6},   # valid voiced frame
            ]
        },
        "keys": {"trajectory": []},
    }

    summary = _build_summary(result, duration_seconds=1.0)

    assert summary["f0_min"] == pytest.approx(220.0)
    assert summary["f0_max"] == pytest.approx(440.0)
    assert summary["f0_min_note"] == "A3"
    assert summary["f0_max_note"] == "A4"
    # Confidence should only reflect voiced-qualified frames (0.8 and 0.6).
    assert summary["confidence"] == pytest.approx(0.7)


def test_is_voiced_frame_applies_bounded_frequency_and_min_salience() -> None:
    from api.routes import _is_voiced_frame

    assert _is_voiced_frame({"f0_hz": 220.0, "confidence": 0.9}) is True
    assert _is_voiced_frame({"f0_hz": 70.0, "confidence": 0.9}) is False
    assert _is_voiced_frame({"f0_hz": 1500.0, "confidence": 0.9}) is False
    assert _is_voiced_frame({"f0_hz": 330.0, "confidence": 0.2}) is False


def test_build_note_events_splits_contiguous_frames_on_note_transitions() -> None:
    from api.routes import _build_note_events

    frame_step = 0.01
    midi_values = [60.1, 60.0, 59.9, 62.1, 62.0, 61.9, 64.1, 64.0, 63.9]
    frames = [
        {
            "time": idx * frame_step,
            "midi": midi,
            "confidence": 0.9,
        }
        for idx, midi in enumerate(midi_values)
    ]

    events = _build_note_events(frames)

    assert len(events) == 3
    assert [round(event["midi"]) for event in events] == [60, 62, 64]
    assert all(event["duration"] > 0.0 for event in events)


def test_build_note_events_splits_on_low_confidence_breaks() -> None:
    from api.routes import _build_note_events

    frame_step = 0.01
    frames = [
        {"time": 0 * frame_step, "midi": 60.0, "confidence": 0.95},
        {"time": 1 * frame_step, "midi": 60.1, "confidence": 0.95},
        {"time": 2 * frame_step, "midi": 59.9, "confidence": 0.95},
        {"time": 3 * frame_step, "midi": 60.0, "confidence": 0.01},
        {"time": 4 * frame_step, "midi": 60.0, "confidence": 0.95},
        {"time": 5 * frame_step, "midi": 60.2, "confidence": 0.95},
        {"time": 6 * frame_step, "midi": 59.8, "confidence": 0.95},
    ]

    events = _build_note_events(frames)

    assert len(events) == 2
    assert events[0]["end"] <= frames[2]["time"]
    assert events[1]["start"] >= frames[4]["time"]


def test_build_evidence_payload_links_low_high_notes_and_guidance_refs() -> None:
    from api.routes import _build_evidence_payload

    pitch_frames = [
        {"time": 0.10, "f0_hz": 220.0, "midi": 57.0, "confidence": 0.95},
        {"time": 0.20, "f0_hz": 246.94, "midi": 59.0, "confidence": 0.95},
        {"time": 0.30, "f0_hz": 329.63, "midi": 64.0, "confidence": 0.95},
        {"time": 0.40, "f0_hz": 440.0, "midi": 69.0, "confidence": 0.95},
    ]

    evidence = _build_evidence_payload(
        pitch_frames,
        note_events=[{"start": 0.1, "end": 0.2}],
        duration_seconds=3.0,
    )

    assert evidence["note_event_count"] == 1
    assert isinstance(evidence["events"], list)
    assert isinstance(evidence["guidance"], list)
    assert evidence["lowest_voiced_note_ref"] == "lowest_voiced_note"
    assert evidence["highest_voiced_note_ref"] == "highest_voiced_note"

    event_by_id = {
        str(event["id"]): event
        for event in evidence["events"]
        if isinstance(event, dict) and event.get("id") is not None
    }
    assert "lowest_voiced_note" in event_by_id
    assert "highest_voiced_note" in event_by_id
    assert "segment_peak_voiced_activity" in event_by_id
    assert "largest_pitch_jump" in event_by_id

    lowest_event = event_by_id[evidence["lowest_voiced_note_ref"]]
    highest_event = event_by_id[evidence["highest_voiced_note_ref"]]

    assert lowest_event["label"] == "Lowest voiced note"
    assert highest_event["label"] == "Highest voiced note"
    assert lowest_event["timestamp_s"] <= highest_event["timestamp_s"]
    assert isinstance(lowest_event.get("timestamp_label"), str)
    assert isinstance(highest_event.get("timestamp_label"), str)

    assert evidence["guidance"]
    for item in evidence["guidance"]:
        assert isinstance(item.get("claim"), str) and item["claim"]
        assert isinstance(item.get("why"), str) and item["why"]
        assert isinstance(item.get("action"), str) and item["action"]
        refs = item.get("evidence_refs")
        assert isinstance(refs, list)
        assert refs
        for ref in refs:
            assert ref in event_by_id


def test_build_calibration_summary_uses_weighted_uncertainty_aggregates() -> None:
    from api.routes import _build_calibration_summary

    summary = _build_calibration_summary(
        {
            "frequency_bins_hz": [100.0, 200.0, 300.0],
            "sample_counts": [3, 2],
            "pitch_bias_cents": [1.0, -2.0],
            "pitch_variance_cents2": [4.0, 9.0],
            "reference_source": "generated_ground_truth_reference",
            "reference_mean_frame_uncertainty_midi": 0.15,
            "reference_voiced_frame_count": 11,
        },
    )

    assert summary["source"] == "generated_ground_truth_reference"
    assert summary["reference_sample_count"] == 5
    assert summary["reference_frequency_min_hz"] == 100.0
    assert summary["reference_frequency_max_hz"] == 300.0
    assert summary["frequency_bin_count"] == 2
    assert summary["populated_frequency_bin_count"] == 2
    assert summary["mean_pitch_bias_cents"] == pytest.approx(-0.2, abs=1e-9)
    assert summary["max_abs_pitch_bias_cents"] == pytest.approx(2.0, abs=1e-9)
    assert summary["mean_pitch_variance_cents2"] == pytest.approx(6.0, abs=1e-9)
    assert summary["pitch_error_mean_cents"] == pytest.approx(-0.2, abs=1e-9)
    assert summary["pitch_error_std_cents"] == pytest.approx(2.8565713714, abs=1e-9)
    assert summary["mean_frame_uncertainty_midi"] == pytest.approx(0.15, abs=1e-9)
    assert summary["voiced_frame_count"] == 11


def test_build_calibration_summary_without_reference_bins_returns_null_bias_metrics() -> None:
    from api.routes import _build_calibration_summary

    summary = _build_calibration_summary(
        {},
    )

    assert summary["source"] == "generated_ground_truth_reference"
    assert summary["reference_sample_count"] == 0
    assert summary["reference_frequency_min_hz"] is None
    assert summary["reference_frequency_max_hz"] is None
    assert summary["frequency_bin_count"] == 0
    assert summary["populated_frequency_bin_count"] == 0
    assert summary["mean_pitch_bias_cents"] is None
    assert summary["max_abs_pitch_bias_cents"] is None
    assert summary["mean_pitch_variance_cents2"] is None
    assert summary["pitch_error_mean_cents"] is None
    assert summary["pitch_error_std_cents"] is None
    assert summary["mean_frame_uncertainty_midi"] is None
    assert summary["voiced_frame_count"] == 0


def test_build_calibration_summary_uses_only_reference_scoped_metadata_fields() -> None:
    from api.routes import _build_calibration_summary

    summary = _build_calibration_summary(
        {
            "frequency_bins_hz": [100.0, 200.0],
            "sample_counts": [4],
            "pitch_bias_cents": [2.0],
            "pitch_variance_cents2": [1.0],
            "reference_mean_frame_uncertainty_midi": 0.25,
            "mean_frame_uncertainty_midi": 9.99,
            "reference_voiced_frame_count": 7,
            "voiced_frame_count": 999,
        }
    )

    assert summary["mean_frame_uncertainty_midi"] == pytest.approx(0.25, abs=1e-9)
    assert summary["voiced_frame_count"] == 7


def test_analyze_accepts_opus_upload(tmp_path, monkeypatch) -> None:
    from api import routes

    _reset_job_state()
    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"

    async def fake_pipeline(file_path: str, metadata=None):
        assert file_path.endswith(".opus")
        routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(file_path).stem
        json_path = routes.OUTPUT_DIR / f"{stem}.json"
        json_path.write_text("{}", encoding="utf-8")
        return {
            "metadata": {
                "filename": (metadata or {}).get("filename"),
                "content_type": (metadata or {}).get("content_type"),
            },
            "summary": {"f0_min": 220.0, "f0_max": 220.0},
            "files": {"json": str(json_path)},
            "result_path": str(json_path),
        }

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            files={"audio": ("sample.opus", b"OPUSDATA", "audio/opus")},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        status = _wait_for_completion(client, job_id)
        assert status["status"] == "completed"

        result_response = client.get(f"/results/{job_id}?format=json")
        assert result_response.status_code == 200
        payload = result_response.json()
        assert payload["metadata"]["filename"] == "sample.opus"
        assert payload["metadata"]["content_type"] == "audio/opus"

    _reset_job_state()


def test_decode_audio_file_opus_failure_is_explicit(monkeypatch) -> None:
    from api import routes

    dummy_librosa = types.SimpleNamespace(load=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no decoder")))
    monkeypatch.setitem(sys.modules, "librosa", dummy_librosa)

    try:
        routes._decode_audio_file("/tmp/broken.opus")
        raise AssertionError("Expected Opus decode failure")
    except RuntimeError as exc:
        message = str(exc)
        assert "Failed to decode Opus audio" in message
        assert "FFmpeg or libsndfile" in message


def test_examples_endpoint_lists_available_tracks(tmp_path, monkeypatch) -> None:
    from api import routes
    from api import config

    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    opus_file = examples_dir / "demo.opus"
    opus_file.write_bytes(b"OPUS")
    (examples_dir / "notes.txt").write_text("not audio", encoding="utf-8")

    monkeypatch.setattr(config, "EXAMPLES_DIR", examples_dir)

    with TestClient(app) as client:
        response = client.get("/examples")
        assert response.status_code == 200
        payload = response.json()
        assert "examples" in payload
        assert len(payload["examples"]) == 1
        assert payload["examples"][0]["id"] == "demo"
        assert payload["examples"][0]["display_name"] == "demo"
        assert payload["examples"][0]["filename"] == "demo.opus"
        assert payload["examples"][0]["content_type"] == "audio/opus"


def test_analyze_example_schedules_job_from_catalog(tmp_path, monkeypatch) -> None:
    from api import routes
    from api import config

    _reset_job_state()
    routes.OUTPUT_DIR = tmp_path / "outputs"

    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    source_file = examples_dir / "demo.opus"
    source_file.write_bytes(b"OPUS")

    monkeypatch.setattr(config, "EXAMPLES_DIR", examples_dir)

    async def fake_pipeline(file_path: str, metadata=None):
        assert Path(file_path).resolve() == source_file.resolve()
        assert (metadata or {}).get("source") == "example"
        assert (metadata or {}).get("example_id") == "demo"
        assert (metadata or {}).get("original_filename") == "demo.opus"
        routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        json_path = routes.OUTPUT_DIR / "demo_result.json"
        json_path.write_text("{}", encoding="utf-8")
        return {
            "metadata": {
                "filename": (metadata or {}).get("filename"),
                "content_type": (metadata or {}).get("content_type"),
                "input_type": (metadata or {}).get("source"),
                "example_id": (metadata or {}).get("example_id"),
                "original_filename": (metadata or {}).get("original_filename"),
            },
            "summary": {"f0_min": 220.0, "f0_max": 220.0},
            "files": {"json": str(json_path)},
            "result_path": str(json_path),
        }

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    with TestClient(app) as client:
        response = client.post("/analyze/example?example_id=demo")
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        status = _wait_for_completion(client, job_id)
        assert status["status"] == "completed"

        result_response = client.get(f"/results/{job_id}?format=json")
        assert result_response.status_code == 200
        payload = result_response.json()
        assert payload["metadata"]["input_type"] == "example"
        assert payload["metadata"]["example_id"] == "demo"
        assert payload["metadata"]["original_filename"] == "demo.opus"

    _reset_job_state()


def test_analyze_example_rejects_unknown_or_non_discoverable_tracks(tmp_path, monkeypatch) -> None:
    from api import routes

    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    (examples_dir / "unsafe.txt").write_text("not audio", encoding="utf-8")

    outside_file = tmp_path / "outside.opus"
    outside_file.write_bytes(b"OPUS")
    linked_file = examples_dir / "linked.opus"
    try:
        linked_file.symlink_to(outside_file)
    except (OSError, NotImplementedError):
        pass

    monkeypatch.setattr(main_routes, "EXAMPLES_DIR", examples_dir)

    with TestClient(app) as client:
        unknown_response = client.post("/analyze/example?example_id=missing")
        assert unknown_response.status_code == 404

        unsupported_response = client.post("/analyze/example?example_id=unsafe")
        assert unsupported_response.status_code == 404

        linked_response = client.post("/analyze/example?example_id=linked")
        assert linked_response.status_code == 404


# ---------------------------------------------------------------------------
# _parse_example_stem – filename metadata extraction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "stem, expected_artist, expected_album, expected_title",
    [
        pytest.param(
            "Nessun Dorma",
            None, None, "Nessun Dorma",
            id="title-only",
        ),
        pytest.param(
            "Maria Callas - Casta Diva",
            "Maria Callas", None, "Casta Diva",
            id="artist-title",
        ),
        pytest.param(
            "Pavarotti - La Bohème - Che Gelida Manina",
            "Pavarotti", "La Bohème", "Che Gelida Manina",
            id="artist-album-title",
        ),
        pytest.param(
            "A - B - C - D",
            "A", "B - C", "D",
            id="multi-segment-album",
        ),
        pytest.param(
            "",
            None, None, "",
            id="empty-string",
        ),
        pytest.param(
            "  Spaced  ",
            None, None, "Spaced",
            id="whitespace-stripped",
        ),
    ],
)
def test_parse_example_stem(stem, expected_artist, expected_album, expected_title):
    from api.routes import _parse_example_stem

    result = _parse_example_stem(stem)

    assert result["artist"] == expected_artist, (
        f"artist mismatch for stem {stem!r}: expected {expected_artist!r}, got {result['artist']!r}"
    )
    assert result["album"] == expected_album, (
        f"album mismatch for stem {stem!r}: expected {expected_album!r}, got {result['album']!r}"
    )
    assert result["title"] == expected_title, (
        f"title mismatch for stem {stem!r}: expected {expected_title!r}, got {result['title']!r}"
    )


# ---------------------------------------------------------------------------
# _build_example_payload – verify title/artist/album keys present
# ---------------------------------------------------------------------------

def test_build_example_payload_includes_metadata_keys(tmp_path):
    from api.routes import _build_example_payload

    audio_file = tmp_path / "sample.opus"
    audio_file.write_bytes(b"OPUSDATA")

    example = {
        "id": "sample",
        "display_name": "Sample Track",
        "title": "Che Gelida Manina",
        "artist": "Pavarotti",
        "album": "La Bohème",
        "content_type": "audio/opus",
    }

    payload = _build_example_payload(example, audio_file)

    assert "title" in payload, "payload missing 'title' key"
    assert "artist" in payload, "payload missing 'artist' key"
    assert "album" in payload, "payload missing 'album' key"

    assert payload["title"] == "Che Gelida Manina", (
        f"expected title 'Che Gelida Manina', got {payload['title']!r}"
    )
    assert payload["artist"] == "Pavarotti", (
        f"expected artist 'Pavarotti', got {payload['artist']!r}"
    )
    assert payload["album"] == "La Bohème", (
        f"expected album 'La Bohème', got {payload['album']!r}"
    )
    assert payload["id"] == "sample"
    assert payload["display_name"] == "Sample Track"
    assert payload["filename"] == "sample.opus"
    assert payload["size_bytes"] == len(b"OPUSDATA")


# ---------------------------------------------------------------------------
# _run_analysis_pipeline — audio_type separation gating
# ---------------------------------------------------------------------------

def test_run_analysis_pipeline_skips_separation_for_isolated(tmp_path, monkeypatch):
    """When audio_type='isolated', separation must NOT be called even if Demucs is available."""
    import numpy as np
    import tempfile
    from unittest.mock import patch as _patch, MagicMock
    import soundfile as sf

    from api import routes

    # Write a minimal wav file so _decode_audio_file can load it
    audio_data = np.zeros(4096, dtype=np.float32)
    wav_path = tmp_path / "test_isolated.wav"
    sf.write(str(wav_path), audio_data, 16000)

    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"
    routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    separate_vocals_called = []

    def fake_separate_vocals(*args, **kwargs):
        separate_vocals_called.append(True)
        raise RuntimeError("should not be called")

    with (
        _patch("analysis.dsp.vocal_separation.is_available", return_value=True),
        _patch("analysis.dsp.vocal_separation.separate_vocals", side_effect=fake_separate_vocals),
        _patch.object(routes, "_VOCAL_SEPARATION_MODE", "auto"),
    ):
        result = routes._run_analysis_pipeline(
            file_path=str(wav_path),
            metadata={"filename": "test.wav", "source": "upload", "audio_type": "isolated"},
        )

    assert not separate_vocals_called, "separate_vocals should NOT be called for isolated audio"
    sep_info = result.get("analysis", {}).get("metadata", {}).get("vocal_separation", {})
    assert sep_info.get("audio_type_requested") == "isolated"
    assert sep_info.get("applied") is False


def test_run_analysis_pipeline_attempts_separation_for_mixed(tmp_path, monkeypatch):
    """When audio_type='mixed' and Demucs unavailable, separation is skipped gracefully."""
    import numpy as np
    import soundfile as sf

    from api import routes

    audio_data = np.zeros(4096, dtype=np.float32)
    wav_path = tmp_path / "test_mixed.wav"
    sf.write(str(wav_path), audio_data, 16000)

    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"
    routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from unittest.mock import patch as _patch

    # Demucs not available → separation skipped, but audio_type_requested is "mixed"
    # Patch the names as bound in api.analysis_core (where _run_analysis_pipeline lives),
    # not the source module — patching the source after import has no effect on already-bound names.
    with (
        _patch("api.analysis_core._vocal_separation_available", return_value=False),
        _patch("api.analysis_core._VOCAL_SEPARATION_MODE", "auto"),
    ):
        result = routes._run_analysis_pipeline(
            file_path=str(wav_path),
            metadata={"filename": "test.wav", "source": "upload", "audio_type": "mixed"},
        )

    sep_info = result.get("analysis", {}).get("metadata", {}).get("vocal_separation", {})
    assert sep_info.get("audio_type_requested") == "mixed"
    assert sep_info.get("applied") is False


def test_run_analysis_pipeline_exposes_pitch_method_diagnostics(tmp_path, monkeypatch):
    """Pitch analysis diagnostics should be present in both summary and per-frame payloads."""
    import numpy as np
    import soundfile as sf

    from api import routes

    audio_data = np.zeros(4096, dtype=np.float32)
    wav_path = tmp_path / "test_diagnostics.wav"
    sf.write(str(wav_path), audio_data, 16000)

    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"
    routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = routes._run_analysis_pipeline(
        file_path=str(wav_path),
        metadata={"filename": "test.wav", "source": "upload", "audio_type": "isolated"},
    )

    analysis = result.get("analysis", {})
    assert "summary" in analysis
    assert "pitch" in analysis

    diagnostics = analysis.get("diagnostics", {}).get("pitch_analysis_methods", {})
    assert "primary_method_used" in diagnostics
    assert "attempted_methods" in diagnostics
    assert "strategy_path" in diagnostics
    assert "fallback_reason" in diagnostics
    assert isinstance(diagnostics.get("method_counts"), dict)
    assert isinstance(diagnostics.get("fallback_reasons"), dict)
    assert isinstance(diagnostics.get("frames_with_diagnostics"), int)

    pitch_frames = analysis.get("pitch", {}).get("frames", [])
    assert isinstance(pitch_frames, list)
    if pitch_frames:
        frame_diag = pitch_frames[0].get("analysis_diagnostics")
        assert isinstance(frame_diag, dict)
        assert "primary_method_used" in frame_diag
        assert "attempted_methods" in frame_diag
        assert "strategy_path" in frame_diag
        assert "fallback_reason" in frame_diag


# ---------------------------------------------------------------------------
# GET /spectrogram/{job_id}  (P2-A)
# ---------------------------------------------------------------------------

def test_spectrogram_endpoint_returns_404_for_unknown_job() -> None:
    """P2-A: GET /spectrogram/{job_id} returns 404 for a nonexistent job."""
    from api.server import app as _app
    _reset_job_state()
    with TestClient(_app) as client:
        resp = client.get("/spectrogram/no-such-job-id")
    assert resp.status_code == 404
    _reset_job_state()


def test_spectrogram_endpoint_returns_200_with_expected_keys(tmp_path, monkeypatch) -> None:
    """P2-A: returns 200 with mix.frames_b64/n_time/n_freq and vocals.available after a
    completed job whose file path is registered in _job_file_paths."""
    import numpy as np
    import struct
    import wave
    from api import routes
    from api.server import app as _app

    _reset_job_state()
    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"

    # Create a minimal valid WAV file (0.1 s of silence, 44100 Hz mono)
    wav_path = tmp_path / "test_audio.wav"
    n_frames = 4410  # 0.1 s at 44100 Hz
    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * n_frames)

    async def fake_pipeline(file_path: str, metadata=None):
        routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return {"metadata": {}, "summary": {}}

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    with TestClient(_app) as client:
        # Upload the WAV file to get a job_id
        with open(wav_path, "rb") as fh:
            resp = client.post(
                "/analyze",
                files={"audio": ("test_audio.wav", fh, "audio/wav")},
            )
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        # Wait for completion
        status = _wait_for_completion(client, job_id, timeout_s=5.0)
        assert status["status"] == "completed"

        # The spectrogram endpoint should return 200 with expected shape
        spec_resp = client.get(f"/spectrogram/{job_id}")
        assert spec_resp.status_code == 200
        payload = spec_resp.json()

        # Top-level keys
        assert "mix" in payload
        assert "vocals" in payload

        mix = payload["mix"]
        assert "frames_b64" in mix
        assert "n_time" in mix
        assert "n_freq" in mix
        assert "freq_min_hz" in mix
        # assert "times_s" in mix
        assert isinstance(mix["n_time"], int) and mix["n_time"] > 0
        assert isinstance(mix["n_freq"], int) and mix["n_freq"] > 0
        assert isinstance(mix["freq_min_hz"], (int, float))

        vocals = payload["vocals"]
        assert "available" in vocals

    _reset_job_state()


def test_spectrogram_endpoint_vocals_available_false_when_demucs_unavailable(tmp_path, monkeypatch) -> None:
    """P2-A: vocals.available=False when Demucs is not installed or cache miss."""
    import wave
    from api import routes
    from api.server import app as _app

    _reset_job_state()
    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"

    # Patch vocal separation to be unavailable
    monkeypatch.setattr(routes, "_vocal_separation_available", lambda: False, raising=False)

    wav_path = tmp_path / "silent.wav"
    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * 4410)

    async def fake_pipeline(file_path: str, metadata=None):
        routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return {"metadata": {}, "summary": {}}

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    with TestClient(_app) as client:
        with open(wav_path, "rb") as fh:
            resp = client.post(
                "/analyze",
                files={"audio": ("silent.wav", fh, "audio/wav")},
            )
        job_id = resp.json()["job_id"]
        _wait_for_completion(client, job_id, timeout_s=5.0)

        spec_resp = client.get(f"/spectrogram/{job_id}")
        assert spec_resp.status_code == 200
        payload = spec_resp.json()
        # Vocals should be unavailable when separation is off and cache is empty
        assert payload["vocals"]["available"] is False

    _reset_job_state()


def test_spectrogram_endpoint_existing_results_endpoint_unchanged(tmp_path, monkeypatch) -> None:
    """P2-A: GET /results/{job_id} payload does NOT contain spectrogram data (AC-6)."""
    from api import routes
    from api.server import app as _app

    _reset_job_state()
    routes.UPLOAD_DIR = tmp_path / "uploads"
    routes.OUTPUT_DIR = tmp_path / "outputs"

    async def fake_pipeline(file_path: str, metadata=None):
        routes.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return {"metadata": {}, "summary": {}, "pitch": {}}

    monkeypatch.setattr(main_routes, "analysis_pipeline", fake_pipeline)

    import wave
    wav_path = tmp_path / "check.wav"
    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * 4410)

    with TestClient(_app) as client:
        with open(wav_path, "rb") as fh:
            resp = client.post("/analyze", files={"audio": ("check.wav", fh, "audio/wav")})
        job_id = resp.json()["job_id"]
        _wait_for_completion(client, job_id, timeout_s=5.0)

        result_resp = client.get(f"/results/{job_id}?format=json")
        assert result_resp.status_code == 200
        result_payload = result_resp.json()
        # Ensure no spectrogram key injected into standard results payload
        assert "spectrogram" not in result_payload
        assert "mix" not in result_payload
        assert "vocals" not in result_payload

    _reset_job_state()
