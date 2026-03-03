"""WebSocket streaming endpoint for real-time vocal comparison.

Clients connect to ``/compare/live?reference_id=<id>`` and stream raw PCM
Float32 LE audio chunks (44 100 Hz mono).  The server responds with
per-chunk feedback, periodic running summaries, and a full session report
on disconnect or ``session_end`` control message.

Binary frame format (client → server):
    Raw PCM Float32 little-endian samples at SESSION_SAMPLE_RATE Hz (mono).
    Frontend must match SESSION_SAMPLE_RATE exactly.

JSON control messages (client → server):
    { "type": "playback_sync", "position_s": <float> }
    { "type": "session_end" }

JSON messages (server → client):
    session_start, chunk_feedback, running_summary, session_report, error
"""
from __future__ import annotations

import dataclasses
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from analysis.comparison import reference_cache as _ref_cache
from analysis.comparison.alignment import align_to_reference, interpolate_reference_at_time
from analysis.comparison.formant_comparison import compare_formants
from analysis.comparison.pitch_comparison import compare_pitch_tracks
from analysis.comparison.range_comparison import compare_vocal_ranges
from analysis.comparison.reference_cache import ReferenceAnalysis
from analysis.comparison.rhythm_comparison import compare_note_timing
from analysis.dsp.peak_detection import detect_harmonics
from analysis.dsp.stft import compute_stft
from analysis.pitch.estimator import estimate_pitch_frames
from analysis.pitch.midi_converter import convert_f0_to_midi
from analysis.pitch.path_optimizer import optimize_lead_voice

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Assumed sample rate for all incoming audio chunks.
# Frontend MUST send PCM Float32 LE at this rate.
SESSION_SAMPLE_RATE: int = 44100

# STFT window size used for streaming pitch extraction.
_STREAMING_NFFT: int = 4096
_STREAMING_HOP: int = 512

# Pitch validity thresholds.
_MIN_VOICED_F0_HZ: float = 20.0
_MIN_VOICED_CONFIDENCE: float = 0.1

# Cents threshold for "in-tune" label.
_IN_TUNE_THRESHOLD_CENTS: float = 50.0

# Send a running_summary every N binary chunks.
_SUMMARY_INTERVAL_CHUNKS: int = 10

# Standard 12-tone note names (C = 0).
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# ---------------------------------------------------------------------------
# Module-level session registry
# ---------------------------------------------------------------------------

_SESSIONS: Dict[str, "ComparisonSession"] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _midi_to_note_name(midi: float) -> str:
    """Return a note name string (e.g. 'A4') for a MIDI value."""
    midi_int = int(round(midi))
    octave = (midi_int // 12) - 1
    name = NOTE_NAMES[midi_int % 12]
    return f"{name}{octave}"


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert a dataclass (possibly nested) to a plain dict."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _dataclass_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_dataclass_to_dict(i) for i in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    return obj


# ---------------------------------------------------------------------------
# StreamingPitchExtractor
# ---------------------------------------------------------------------------


class StreamingPitchExtractor:
    """Maintains a ring buffer of incoming audio samples and extracts pitch
    from overlapping STFT windows.

    The extractor keeps the last ``n_fft * 2`` samples in an internal buffer.
    Once at least ``n_fft`` total samples have been pushed, it runs the full
    pitch pipeline on a single ``n_fft``-length window.

    Args:
        sample_rate: Audio sample rate (must match SESSION_SAMPLE_RATE).
        n_fft: STFT window length in samples.
        hop_length: STFT hop length (used for time-stamp computation).
    """

    def __init__(
        self,
        sample_rate: int = SESSION_SAMPLE_RATE,
        n_fft: int = _STREAMING_NFFT,
        hop_length: int = _STREAMING_HOP,
    ) -> None:
        self.sample_rate = sample_rate
        self.n_fft = n_fft
        self.hop_length = hop_length
        # Internal ring buffer — always keep last n_fft * 2 samples.
        self._buffer: np.ndarray = np.zeros(n_fft * 2, dtype=np.float32)
        self._write_pos: int = 0  # Next write position in the buffer.
        self._total_samples: int = 0  # Total samples pushed since creation.

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push(self, chunk: np.ndarray) -> Optional[Dict[str, Any]]:
        """Push a new audio chunk into the buffer.

        Returns a pitch estimate dict ``{ f0_hz, midi, note_name, confidence,
        time_s }`` when enough data is available; returns ``None`` if pitch
        extraction yields an unvoiced or low-confidence estimate.

        Args:
            chunk: 1-D float32 array of audio samples.
        """
        chunk = np.asarray(chunk, dtype=np.float32)
        n = chunk.size
        if n == 0:
            return None

        buf_len = self._buffer.size
        if n >= buf_len:
            # Chunk larger than buffer — keep only the last buf_len samples.
            self._buffer[:] = chunk[-buf_len:]
            self._write_pos = 0
        else:
            end = self._write_pos + n
            if end <= buf_len:
                self._buffer[self._write_pos : end] = chunk
            else:
                first = buf_len - self._write_pos
                self._buffer[self._write_pos :] = chunk[:first]
                self._buffer[: n - first] = chunk[first:]
            self._write_pos = end % buf_len

        self._total_samples += n

        if self._total_samples < self.n_fft:
            return None

        return self._extract_pitch()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_window(self) -> np.ndarray:
        """Return the last ``n_fft`` samples from the circular buffer."""
        buf_len = self._buffer.size
        nfft = self.n_fft
        if nfft > buf_len:
            return np.zeros(nfft, dtype=np.float32)
        wp = self._write_pos
        start = (wp - nfft) % buf_len
        if start + nfft <= buf_len:
            return self._buffer[start : start + nfft].copy()
        # Wraps around.
        part1 = self._buffer[start:]
        part2 = self._buffer[: nfft - len(part1)]
        return np.concatenate([part1, part2])

    def _extract_pitch(self) -> Optional[Dict[str, Any]]:
        """Run the pitch pipeline on the current window and return a dict."""
        window = self._get_window()
        time_s = float(self._total_samples) / float(self.sample_rate)

        try:
            stft_result = compute_stft(
                window,
                self.sample_rate,
                n_fft=self.n_fft,
                hop_length=self.hop_length,
            )
        except Exception:
            logger.exception("streaming.stft_error")
            return None

        spectrum = stft_result.spectrum  # shape (n_fft//2+1, n_frames)
        frequencies = stft_result.frequencies
        sigma_f = stft_result.sigma_f

        # We only want the last frame for latency reasons.
        if spectrum.shape[1] == 0:
            return None

        try:
            harmonic_frames = detect_harmonics(spectrum, frequencies)
        except Exception:
            logger.exception("streaming.harmonics_error")
            return None

        if not harmonic_frames:
            return None

        try:
            pitch_frames = estimate_pitch_frames(
                spectrum,
                frequencies,
                harmonic_frames,
                window,
                self.sample_rate,
                self.hop_length,
            )
        except Exception:
            logger.exception("streaming.pitch_frames_error")
            return None

        if not pitch_frames:
            return None

        try:
            path = optimize_lead_voice(pitch_frames)
        except Exception:
            logger.exception("streaming.optimize_path_error")
            return None

        # Pick the last (most recent) frame.
        idx = len(path.f0_hz) - 1
        f0 = float(path.f0_hz[idx])
        confidence = float(path.salience[idx])

        if f0 <= _MIN_VOICED_F0_HZ or confidence < _MIN_VOICED_CONFIDENCE:
            return None

        f0_arr = np.array([f0], dtype=np.float32)
        sigma_arr = np.array([float(sigma_f[0])], dtype=np.float32)

        try:
            midi_arr, _ = convert_f0_to_midi(f0_arr, sigma_f=sigma_arr)
        except Exception:
            logger.exception("streaming.midi_convert_error")
            return None

        midi_val = float(midi_arr[0])
        if midi_val <= 0.0:
            return None

        note_name = _midi_to_note_name(midi_val)
        return {
            "f0_hz": round(f0, 3),
            "midi": round(midi_val, 3),
            "note_name": note_name,
            "confidence": round(confidence, 4),
            "time_s": round(time_s, 4),
        }


# ---------------------------------------------------------------------------
# ComparisonSession
# ---------------------------------------------------------------------------


@dataclass
class ComparisonSession:
    """State for a single active WebSocket comparison session.

    Attributes:
        session_id: UUID4 hex identifying this session.
        reference_id: ID of the cached reference being compared against.
        reference: Loaded ``ReferenceAnalysis`` object.
        extractor: Per-session ``StreamingPitchExtractor`` instance.
        current_position_s: Current playback position as reported by client.
        start_time: Monotonic timestamp of session creation.
        chunk_results: List of per-chunk feedback dicts (voiced only).
        chunk_count: Total binary frames received (voiced + unvoiced).
    """

    session_id: str
    reference_id: str
    reference: ReferenceAnalysis
    extractor: StreamingPitchExtractor
    current_position_s: float = 0.0
    start_time: float = field(default_factory=time.monotonic)
    chunk_results: List[Dict[str, Any]] = field(default_factory=list)
    chunk_count: int = 0


# ---------------------------------------------------------------------------
# Session aggregation helpers
# ---------------------------------------------------------------------------


def _compute_pitch_deviation_cents(user_midi: float, ref_f0_hz: float) -> Optional[float]:
    """Return signed deviation in cents between user MIDI and reference f0."""
    if ref_f0_hz <= 0.0 or user_midi <= 0.0:
        return None
    ref_midi = 69.0 + 12.0 * math.log2(ref_f0_hz / 440.0)
    return (user_midi - ref_midi) * 100.0


def _build_running_summary(session: ComparisonSession) -> Dict[str, Any]:
    """Build a ``running_summary`` message from session state."""
    elapsed = time.monotonic() - session.start_time
    total = session.chunk_count
    voiced = len(session.chunk_results)

    deviations = [
        r["pitch_deviation_cents"]
        for r in session.chunk_results
        if r.get("pitch_deviation_cents") is not None
    ]

    mean_dev: Optional[float] = None
    accuracy: Optional[float] = None
    if deviations:
        mean_dev = round(float(np.mean(np.abs(deviations))), 3)
        in_tune_count = sum(1 for d in deviations if abs(d) <= _IN_TUNE_THRESHOLD_CENTS)
        accuracy = round(in_tune_count / len(deviations), 4)

    return {
        "type": "running_summary",
        "session_elapsed_s": round(elapsed, 2),
        "voiced_chunk_count": voiced,
        "total_chunk_count": total,
        "mean_pitch_deviation_cents": mean_dev,
        "pitch_accuracy_ratio": accuracy,
        "mean_onset_error_ms": None,
    }


def _build_session_report(session: ComparisonSession) -> Dict[str, Any]:
    """Aggregate session results and produce the final ``session_report`` dict."""
    ref = session.reference
    elapsed = time.monotonic() - session.start_time

    # Build a user pitch track from voiced chunk results.
    user_pitch_track = [
        {
            "time_s": r["timestamp_s"],
            "f0_hz": r["user_f0_hz"],
            "midi": r["user_midi"],
            "note_name": r.get("user_note_name"),
            "confidence": r.get("user_confidence", 0.0),
        }
        for r in session.chunk_results
        if r.get("user_f0_hz") is not None
    ]

    # Align user to reference.
    aligned_pairs = align_to_reference(user_pitch_track, ref.pitch_track, 0.0)

    # Pitch comparison.
    try:
        pitch_result = compare_pitch_tracks(aligned_pairs)
        pitch_dict = _dataclass_to_dict(pitch_result)
    except Exception:
        logger.exception("session_report.pitch_compare_error")
        pitch_dict = {}

    # Rhythm comparison — build minimal note events from voiced frames.
    user_voiced_midi = [float(r["user_midi"]) for r in session.chunk_results if r.get("user_midi")]
    try:
        user_note_events = _infer_note_events_from_pitch_track(user_pitch_track)
        rhythm_result = compare_note_timing(user_note_events, ref.note_events)
        rhythm_dict = _dataclass_to_dict(rhythm_result)
    except Exception:
        logger.exception("session_report.rhythm_compare_error")
        rhythm_dict = {}

    # Range comparison.
    try:
        user_tessitura = {}
        range_result = compare_vocal_ranges(user_voiced_midi, ref.note_events, user_tessitura)
        range_dict = _dataclass_to_dict(range_result)
    except Exception:
        logger.exception("session_report.range_compare_error")
        range_dict = {}

    # Formant comparison.
    try:
        user_formant_summary: Optional[Dict[str, Any]] = None  # Not available in streaming mode.
        formant_result = compare_formants(user_formant_summary, ref.formant_summary)
        formant_dict = _dataclass_to_dict(formant_result)
    except Exception:
        logger.exception("session_report.formant_compare_error")
        formant_dict = {}

    return {
        "type": "session_report",
        "session_id": session.session_id,
        "reference_id": session.reference_id,
        "duration_s": round(elapsed, 2),
        "comparison": {
            "pitch": pitch_dict,
            "rhythm": rhythm_dict,
            "range": range_dict,
            "formants": formant_dict,
        },
    }


def _infer_note_events_from_pitch_track(pitch_track: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert a streaming pitch track into coarse note event segments.

    Groups consecutive voiced frames within 0.5 semitone of each other into
    a single note event.  Used for rhythm comparison in the session report.
    """
    if not pitch_track:
        return []

    events: List[Dict[str, Any]] = []
    current_start: float = pitch_track[0]["time_s"]
    current_midi: float = pitch_track[0]["midi"]

    for frame in pitch_track[1:]:
        midi = frame["midi"]
        t = frame["time_s"]
        if abs(midi - current_midi) > 0.5:
            events.append(
                {
                    "start_s": current_start,
                    "end_s": t,
                    "midi": current_midi,
                    "note_name": _midi_to_note_name(current_midi),
                    "duration_s": t - current_start,
                }
            )
            current_start = t
            current_midi = midi

    # Close last event.
    last_t = pitch_track[-1]["time_s"]
    if last_t > current_start:
        events.append(
            {
                "start_s": current_start,
                "end_s": last_t,
                "midi": current_midi,
                "note_name": _midi_to_note_name(current_midi),
                "duration_s": last_t - current_start,
            }
        )

    return events


# ---------------------------------------------------------------------------
# Router and WebSocket endpoint
# ---------------------------------------------------------------------------

streaming_router = APIRouter()


@streaming_router.websocket("/compare/live")
async def live_comparison(websocket: WebSocket, reference_id: str = Query(...)) -> None:
    """Real-time vocal comparison WebSocket endpoint.

    Query parameters:
        reference_id: ID of a cached ``ReferenceAnalysis`` (obtained via
            ``POST /reference/upload`` or ``POST /reference/from-example/{id}``).

    Binary frames (client → server):
        Raw PCM Float32 little-endian samples at ``SESSION_SAMPLE_RATE`` Hz.

    Text frames (client → server):
        JSON control messages (see module docstring).
    """
    await websocket.accept()

    # --- Validate reference ----------------------------------------------------
    ref: Optional[ReferenceAnalysis] = _ref_cache.get(reference_id)
    if ref is None:
        await websocket.close(code=4004, reason="reference_not_found")
        logger.warning("ws.live_comparison reference_not_found id=%s", reference_id)
        return

    # --- Create session --------------------------------------------------------
    session_id = uuid4().hex
    session = ComparisonSession(
        session_id=session_id,
        reference_id=reference_id,
        reference=ref,
        extractor=StreamingPitchExtractor(
            sample_rate=SESSION_SAMPLE_RATE,
            n_fft=_STREAMING_NFFT,
            hop_length=_STREAMING_HOP,
        ),
    )
    _SESSIONS[session_id] = session

    logger.info("ws.live_comparison.start session=%s reference=%s", session_id, reference_id)

    # --- Send session_start message --------------------------------------------
    await websocket.send_text(
        json.dumps(
            {
                "type": "session_start",
                "session_id": session_id,
                "reference_id": reference_id,
                "reference_duration_s": ref.duration_s,
                "reference_note_count": len(ref.note_events),
            }
        )
    )

    # --- Main receive loop -----------------------------------------------------
    try:
        while True:
            msg = await websocket.receive()

            # ------------------------------------------------------------------
            # Binary frames: audio chunks
            # ------------------------------------------------------------------
            if "bytes" in msg and msg["bytes"] is not None:
                raw_bytes: bytes = msg["bytes"]
                if len(raw_bytes) % 4 != 0:
                    logger.warning(
                        "ws.audio_chunk.bad_length session=%s len=%d",
                        session_id,
                        len(raw_bytes),
                    )
                    continue

                audio_chunk = np.frombuffer(raw_bytes, dtype=np.float32)
                session.chunk_count += 1

                pitch_estimate = session.extractor.push(audio_chunk)

                chunk_ts = session.current_position_s

                # Build chunk_feedback message.
                if pitch_estimate is not None:
                    user_f0 = pitch_estimate["f0_hz"]
                    user_midi = pitch_estimate["midi"]
                    user_note = pitch_estimate["note_name"]
                    user_conf = pitch_estimate["confidence"]

                    # Query reference at current playback position.
                    ref_frame = interpolate_reference_at_time(ref.pitch_track, chunk_ts)

                    ref_f0: Optional[float] = None
                    ref_midi: Optional[float] = None
                    ref_note: Optional[str] = None
                    deviation: Optional[float] = None
                    in_tune: Optional[bool] = None

                    if ref_frame is not None:
                        ref_f0 = ref_frame.get("f0_hz")
                        if ref_f0 and ref_f0 > 0:
                            ref_midi_val = ref_frame.get("midi")
                            if ref_midi_val:
                                ref_midi = round(float(ref_midi_val), 3)
                                ref_note = ref_frame.get("note_name") or _midi_to_note_name(ref_midi)
                            deviation = _compute_pitch_deviation_cents(user_midi, float(ref_f0))
                            if deviation is not None:
                                in_tune = abs(deviation) <= _IN_TUNE_THRESHOLD_CENTS
                                deviation = round(deviation, 3)

                    feedback: Dict[str, Any] = {
                        "type": "chunk_feedback",
                        "timestamp_s": round(chunk_ts, 4),
                        "user_f0_hz": user_f0,
                        "user_midi": user_midi,
                        "user_note_name": user_note,
                        "user_confidence": user_conf,
                        "reference_f0_hz": round(float(ref_f0), 3) if ref_f0 else None,
                        "reference_midi": ref_midi,
                        "reference_note_name": ref_note,
                        "pitch_deviation_cents": deviation,
                        "in_tune": in_tune,
                    }
                    session.chunk_results.append(feedback)
                    await websocket.send_text(json.dumps(feedback))
                else:
                    # Unvoiced chunk — send minimal feedback.
                    feedback = {
                        "type": "chunk_feedback",
                        "timestamp_s": round(chunk_ts, 4),
                        "user_f0_hz": None,
                        "user_midi": None,
                        "user_note_name": None,
                        "user_confidence": None,
                        "reference_f0_hz": None,
                        "reference_midi": None,
                        "reference_note_name": None,
                        "pitch_deviation_cents": None,
                        "in_tune": None,
                    }
                    await websocket.send_text(json.dumps(feedback))

                # Periodic running summary.
                if session.chunk_count % _SUMMARY_INTERVAL_CHUNKS == 0:
                    await websocket.send_text(json.dumps(_build_running_summary(session)))

            # ------------------------------------------------------------------
            # Text frames: control messages
            # ------------------------------------------------------------------
            elif "text" in msg and msg["text"] is not None:
                try:
                    ctrl = json.loads(msg["text"])
                except json.JSONDecodeError:
                    logger.warning("ws.ctrl.bad_json session=%s", session_id)
                    continue

                msg_type = ctrl.get("type")

                if msg_type == "playback_sync":
                    pos = ctrl.get("position_s")
                    if pos is not None:
                        session.current_position_s = float(pos)
                        logger.debug(
                            "ws.playback_sync session=%s position_s=%.3f",
                            session_id,
                            session.current_position_s,
                        )

                elif msg_type == "session_end":
                    logger.info("ws.session_end.requested session=%s", session_id)
                    report = _build_session_report(session)
                    await websocket.send_text(json.dumps(report))
                    break

                else:
                    logger.debug("ws.ctrl.unknown type=%s session=%s", msg_type, session_id)

            # ------------------------------------------------------------------
            # Disconnect signal from FastAPI
            # ------------------------------------------------------------------
            elif msg.get("type") == "websocket.disconnect":
                logger.info("ws.disconnect session=%s", session_id)
                break

    except WebSocketDisconnect:
        logger.info("ws.live_comparison.disconnect session=%s", session_id)
    except Exception:
        logger.exception("ws.live_comparison.error session=%s", session_id)
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "Internal server error during streaming."})
            )
        except Exception:
            pass
    finally:
        # Always send final report if the session accumulated any results.
        if session.chunk_count > 0:
            try:
                report = _build_session_report(session)
                await websocket.send_text(json.dumps(report))
            except Exception:
                logger.debug("ws.final_report.send_failed session=%s", session_id)

        _SESSIONS.pop(session_id, None)
        logger.info(
            "ws.live_comparison.closed session=%s chunks=%d voiced=%d",
            session_id,
            session.chunk_count,
            len(session.chunk_results),
        )


__all__ = [
    "streaming_router",
    "StreamingPitchExtractor",
    "ComparisonSession",
    "SESSION_SAMPLE_RATE",
]
