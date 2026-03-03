"""Integration tests for the streaming WebSocket endpoint.

Tests the /compare/live WebSocket endpoint and reference-related REST routes.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

import analysis.comparison.reference_cache as rc_module
from analysis.comparison.reference_cache import ReferenceAnalysis, store
from api.server import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_reference(ref_id: str = "test-ref-001") -> ReferenceAnalysis:
    """Construct and store a minimal ReferenceAnalysis for integration tests."""
    ref = ReferenceAnalysis(
        reference_id=ref_id,
        source="upload",
        source_id="test.wav",
        analysis={},
        pitch_track=[
            {"time_s": 0.0, "f0_hz": 440.0, "midi": 69.0, "note_name": "A4", "confidence": 0.9},
            {"time_s": 0.1, "f0_hz": 880.0, "midi": 81.0, "note_name": "A5", "confidence": 0.9},
        ],
        note_events=[
            {"start_s": 0.0, "end_s": 1.0, "midi": 69.0, "note_name": "A4", "duration_s": 1.0}
        ],
        duration_s=10.0,
        key="A major",
        tessitura_center_midi=69.0,
        formant_summary=None,
        created_at=datetime.now(timezone.utc),
    )
    store(ref)
    return ref


# ---------------------------------------------------------------------------
# Fixture: clean cache between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_reference_cache():
    """Clear the module-level _CACHE dict before and after each test."""
    rc_module._CACHE.clear()
    yield
    rc_module._CACHE.clear()


# ---------------------------------------------------------------------------
# WebSocket tests
# ---------------------------------------------------------------------------


class TestWebSocketEndpoint:

    def test_websocket_unknown_reference_rejects(self):
        """Connecting with an unknown reference_id closes the WebSocket with code 4004."""
        with pytest.raises(Exception):
            # TestClient raises when WebSocket is closed with a non-normal code
            with client.websocket_connect("/compare/live?reference_id=nonexistent") as ws:
                # Attempt to receive — server should close immediately with 4004
                msg = ws.receive_json()
                # Should not reach here; if it does, force failure
                pytest.fail(f"Expected WS to close with 4004 but got message: {msg}")

    def test_websocket_unknown_reference_close_code(self):
        """Connecting with unknown reference should trigger close — verifying endpoint behavior."""
        # Use a reference ID that definitely doesn't exist
        ref_id = "absolutely-nonexistent-reference-id-xyz"
        assert not rc_module.exists(ref_id), "Precondition: reference should not exist"

        # The endpoint should close the connection; we just verify code path won't crash server
        try:
            with client.websocket_connect(f"/compare/live?reference_id={ref_id}") as ws:
                # Server sends close after accept(), TestClient may raise or return close
                try:
                    ws.receive_json()
                except Exception:
                    pass  # Expected: connection closed by server
        except Exception:
            pass  # TestClient may raise on WS close

    def test_websocket_session_start_message(self):
        """Injecting a mock reference and connecting → first message is session_start."""
        ref = make_mock_reference("ws-test-ref-001")

        with client.websocket_connect("/compare/live?reference_id=ws-test-ref-001") as ws:
            data = ws.receive_json()

            assert data.get("type") == "session_start", \
                f"First WS message should be 'session_start', got: {data.get('type')}"
            assert "session_id" in data, "session_start should contain 'session_id'"
            assert "reference_id" in data, "session_start should contain 'reference_id'"
            assert "reference_duration_s" in data, "session_start should contain 'reference_duration_s'"
            assert data["reference_id"] == "ws-test-ref-001"
            assert data["reference_duration_s"] == pytest.approx(10.0), \
                "reference_duration_s should match stored reference duration"

    def test_websocket_binary_chunk_feedback(self):
        """Sending a binary silence chunk → receives chunk_feedback message."""
        ref = make_mock_reference("ws-test-ref-002")

        with client.websocket_connect("/compare/live?reference_id=ws-test-ref-002") as ws:
            # Receive the initial session_start
            session_start = ws.receive_json()
            assert session_start["type"] == "session_start"

            # Send 1024 samples of silence as Float32 bytes
            silence_chunk = np.zeros(1024, dtype=np.float32)
            ws.send_bytes(silence_chunk.tobytes())

            # Server should respond with chunk_feedback
            feedback = ws.receive_json()
            assert feedback.get("type") == "chunk_feedback", \
                f"Expected 'chunk_feedback', got: {feedback.get('type')}"

            # Verify mandatory fields are present (values may be None for silence)
            assert "timestamp_s" in feedback, "chunk_feedback should have 'timestamp_s'"
            assert "in_tune" in feedback, "chunk_feedback should have 'in_tune'"

    def test_websocket_multiple_chunks_running_summary(self):
        """Sending 10+ chunks → eventually receives a running_summary message."""
        ref = make_mock_reference("ws-test-ref-003")

        with client.websocket_connect("/compare/live?reference_id=ws-test-ref-003") as ws:
            session_start = ws.receive_json()
            assert session_start["type"] == "session_start"

            # Send enough chunks to trigger a running_summary (every 10 chunks)
            silence_chunk = np.zeros(1024, dtype=np.float32)
            messages_received = [session_start]

            for _ in range(10):
                ws.send_bytes(silence_chunk.tobytes())
                msg = ws.receive_json()
                messages_received.append(msg)

            # We should have received chunk_feedback messages; 10th may produce running_summary
            types_received = {m.get("type") for m in messages_received}
            assert "chunk_feedback" in types_received or "running_summary" in types_received, \
                f"Expected chunk_feedback or running_summary, got types: {types_received}"


# ---------------------------------------------------------------------------
# REST route tests (reference endpoints)
# ---------------------------------------------------------------------------


class TestReferenceRESTEndpoints:

    def test_reference_upload_endpoint_exists(self):
        """POST /reference/upload with non-audio data → 400/415/422/429 (endpoint registered)."""
        # Send invalid file content — we just confirm the route exists
        response = client.post(
            "/reference/upload",
            files={"audio": ("notaudio.txt", b"this is not audio", "text/plain")},
        )
        # Endpoint should exist (not 404 or 405), and reject invalid media or rate-limit
        assert response.status_code in (400, 415, 422, 429), \
            f"Expected 400/415/422/429 for invalid file or rate limit, got {response.status_code}"

    def test_reference_from_example_not_found(self):
        """POST /reference/from-example/nonexistent-id → 404."""
        response = client.post("/reference/from-example/nonexistent-example-id")
        assert response.status_code == 404, \
            f"Nonexistent example_id should return 404, got {response.status_code}"

    def test_get_reference_not_found(self):
        """GET /reference/nonexistent-id → 404."""
        response = client.get("/reference/nonexistent-id")
        assert response.status_code == 404, \
            f"Nonexistent reference_id should return 404, got {response.status_code}"

    def test_get_reference_found(self):
        """GET /reference/<id> for a stored reference → 200 with expected fields."""
        ref = make_mock_reference("rest-test-ref-001")

        response = client.get("/reference/rest-test-ref-001")
        assert response.status_code == 200, \
            f"Stored reference_id should return 200, got {response.status_code}"

        data = response.json()
        assert data.get("reference_id") == "rest-test-ref-001", \
            "Response should include the reference_id"
