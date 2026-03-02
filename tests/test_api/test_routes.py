import asyncio
import sys
import time
from pathlib import Path
import types

import pytest
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
    (examples_dir / "notes.txt").write_text("not audio", encoding="utf-8")

    monkeypatch.setattr(routes, "EXAMPLES_DIR", examples_dir)

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

    _reset_job_state()
    routes.OUTPUT_DIR = tmp_path / "outputs"

    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    source_file = examples_dir / "demo.opus"
    source_file.write_bytes(b"OPUS")

    monkeypatch.setattr(routes, "EXAMPLES_DIR", examples_dir)

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

    monkeypatch.setattr(routes, "analysis_pipeline", fake_pipeline)

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

    monkeypatch.setattr(routes, "EXAMPLES_DIR", examples_dir)

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
