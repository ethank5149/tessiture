import asyncio
import sys
import time
from pathlib import Path
import types

from fastapi.testclient import TestClient

from api import job_manager
from api.server import app


def _reset_job_state() -> None:
    for task in list(job_manager._tasks.values()):
        if not task.done():
            task.cancel()
    job_manager._tasks.clear()
    job_manager._jobs.clear()


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
                "overall_confidence": 1.0,
            },
            "files": {
                "json": str(json_path),
                "csv": str(csv_path),
                "pdf": str(pdf_path),
            },
            "result_path": str(json_path),
        }

    monkeypatch.setattr(routes, "analysis_pipeline", fake_pipeline)

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

        result_response = client.get(f"/results/{job_id}?format=json")
        assert result_response.status_code == 200
        result_payload = result_response.json()
        assert "summary" in result_payload
        assert result_payload["summary"]["f0_min"] == 440.0

    _reset_job_state()


def test_results_downloads_csv_and_pdf(tmp_path, monkeypatch) -> None:
    from api import routes

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

    monkeypatch.setattr(routes, "analysis_pipeline", fake_pipeline)

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

    monkeypatch.setattr(routes, "analysis_pipeline", fake_pipeline)

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

    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    opus_file = examples_dir / "demo.opus"
    opus_file.write_bytes(b"OPUS")

    monkeypatch.setattr(routes, "EXAMPLES_DIR", examples_dir)
    monkeypatch.setattr(
        routes,
        "EXAMPLE_TRACKS",
        [
            {
                "id": "demo-1",
                "display_name": "Demo Example",
                "filename": "demo.opus",
                "content_type": "audio/opus",
            }
        ],
    )

    with TestClient(app) as client:
        response = client.get("/examples")
        assert response.status_code == 200
        payload = response.json()
        assert "examples" in payload
        assert len(payload["examples"]) == 1
        assert payload["examples"][0]["id"] == "demo-1"
        assert payload["examples"][0]["display_name"] == "Demo Example"
        assert payload["examples"][0]["filename"] == "demo.opus"
        assert payload["examples"][0]["content_type"] == "audio/opus"


def test_analyze_example_schedules_job_from_catalog(tmp_path, monkeypatch) -> None:
    from api import routes

    _reset_job_state()
    routes.OUTPUT_DIR = tmp_path / "outputs"

    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    source_file = examples_dir / "demo.opus"
    source_file.write_bytes(b"OPUS")

    monkeypatch.setattr(routes, "EXAMPLES_DIR", examples_dir)
    monkeypatch.setattr(
        routes,
        "EXAMPLE_TRACKS",
        [
            {
                "id": "demo-1",
                "display_name": "Demo Example",
                "filename": "demo.opus",
                "content_type": "audio/opus",
            }
        ],
    )

    async def fake_pipeline(file_path: str, metadata=None):
        assert Path(file_path).resolve() == source_file.resolve()
        assert (metadata or {}).get("source") == "example"
        assert (metadata or {}).get("example_id") == "demo-1"
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

    monkeypatch.setattr(routes, "analysis_pipeline", fake_pipeline)

    with TestClient(app) as client:
        response = client.post("/analyze/example?example_id=demo-1")
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        status = _wait_for_completion(client, job_id)
        assert status["status"] == "completed"

        result_response = client.get(f"/results/{job_id}?format=json")
        assert result_response.status_code == 200
        payload = result_response.json()
        assert payload["metadata"]["input_type"] == "example"
        assert payload["metadata"]["example_id"] == "demo-1"
        assert payload["metadata"]["original_filename"] == "demo.opus"

    _reset_job_state()


def test_analyze_example_rejects_unknown_or_unsafe_catalog_entries(tmp_path, monkeypatch) -> None:
    from api import routes

    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(routes, "EXAMPLES_DIR", examples_dir)
    monkeypatch.setattr(
        routes,
        "EXAMPLE_TRACKS",
        [
            {
                "id": "unsafe",
                "display_name": "Unsafe",
                "filename": "../outside.opus",
                "content_type": "audio/opus",
            }
        ],
    )

    with TestClient(app) as client:
        unknown_response = client.post("/analyze/example?example_id=missing")
        assert unknown_response.status_code == 404

        unsafe_response = client.post("/analyze/example?example_id=unsafe")
        assert unsafe_response.status_code == 500
        assert "misconfigured" in unsafe_response.json()["detail"].lower()
