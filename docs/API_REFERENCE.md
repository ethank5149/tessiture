# Tessiture — API Reference

**Last updated:** 2026-03-04

This document covers all HTTP and WebSocket endpoints, the result JSON schema, and environment-variable configuration.

For system architecture, see [ARCHITECTURE.md](ARCHITECTURE.md).
For deployment, see [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Table of Contents

1. [Endpoints](#1-endpoints)
2. [Result Structure](#2-result-structure)
3. [Configuration](#3-configuration)
4. [Rate Limiting](#4-rate-limiting)
5. [Error Responses](#5-error-responses)

---

## 1. Endpoints

### `POST /analyze`

Uploads an audio file and schedules background analysis.

- **Multipart field:** `audio`
- **Accepted extensions** (default): `.wav`, `.mp3`, `.flac`, `.m4a`, `.opus`
- **Accepted MIME types** (default): `audio/wav`, `audio/x-wav`, `audio/mpeg`, `audio/flac`, `audio/x-flac`, `audio/mp4`, `audio/opus`, `audio/x-opus`, `audio/ogg`, `application/ogg`

**Response:**

```json
{
  "job_id": "2d7e5c3b-...",
  "status_url": "/status/2d7e5c3b-...",
  "results_url": "/results/2d7e5c3b-..."
}
```

### `GET /status/{job_id}`

Returns job metadata and progress.

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | UUID |
| `status` | string | `queued`, `processing`, `completed`, `failed` |
| `progress` | integer | 0–100 |
| `stage` | string | Current pipeline stage name |
| `message` | string | Human-readable status message |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |
| `result_path` | string | Path to result artifact (when completed) |
| `error` | string | Error text (when failed) |

### `GET /results/{job_id}?format={json|csv|pdf}`

- `format=json` — Full structured analysis payload (default)
- `format=csv` — Downloadable CSV file
- `format=pdf` — Downloadable PDF report

### `GET /examples`

Lists available example tracks from the server's example library.

### `POST /examples/{id}/analyze`

Triggers analysis of an example track by its ID.

### `GET /compare/references`

Lists available reference tracks for comparison sessions.

### `WS /compare/live?reference_id={id}`

WebSocket endpoint for real-time vocal comparison.

**Binary frames (client → server):** Raw PCM Float32 little-endian samples at 44,100 Hz mono.

**JSON control messages (client → server):**

```json
{ "type": "playback_sync", "position_s": 12.5 }
{ "type": "session_end" }
```

**JSON messages (server → client):**

| Type | When | Content |
|------|------|---------|
| `session_start` | On connect | Session ID, reference metadata |
| `chunk_feedback` | Per audio chunk | Pitch deviation, note name, confidence |
| `running_summary` | Every 10 chunks | Accuracy ratio, bias, stability |
| `session_report` | On session end | Full comparison report |
| `error` | On error | Error message |

---

## 2. Result Structure

JSON results contain normalized sections:

```json
{
  "metadata": {
    "analysis_version": "0.1.0",
    "sample_rate": 44100,
    "hop_length": 512,
    "duration_seconds": 12.4
  },
  "summary": {
    "f0_min": 196.0,
    "f0_max": 440.0,
    "f0_min_note": "G3",
    "f0_max_note": "A4",
    "tessitura_range": [57.0, 69.0],
    "tessitura_range_notes": ["A3", "A4"],
    "overall_confidence": 0.82
  },
  "pitch": {
    "frames": [
      {
        "index": 0,
        "time": 0.0,
        "f0_hz": 220.0,
        "midi": 57.0,
        "note": "A3",
        "cents": 0.0,
        "confidence": 0.91,
        "uncertainty": 0.12
      }
    ]
  },
  "note_events": [
    {
      "start_time": 0.0,
      "end_time": 0.5,
      "midi": 57,
      "note": "A3",
      "duration_s": 0.5,
      "mean_confidence": 0.89
    }
  ],
  "chords": [ ... ],
  "keys": [ ... ],
  "tessitura": {
    "metrics": {
      "comfort_center": 62.85,
      "comfort_band": [60.0, 66.0],
      "tessitura_band": [57.0, 69.0],
      "variance": 5.3,
      "std_dev": 2.3,
      "mean_variance": 0.00014,
      "strain_zones": [ ... ]
    }
  },
  "advanced": {
    "vibrato": { "rate_hz": 5.5, "depth_cents": 42.0, "valid": true },
    "formants": { ... },
    "phrase_boundaries": [ ... ]
  },
  "uncertainty": { ... },
  "inferential_statistics": {
    "preset": "casual",
    "confidence_level": 0.95,
    "n_bootstrap_samples": 1000,
    "metrics": {
      "f0_mean_hz": {
        "estimate": 220.5,
        "ci_low": 218.2,
        "ci_high": 222.8,
        "p_value": 0.003,
        "n_samples": 450
      }
    }
  },
  "calibration": { ... },
  "files": {
    "json": "/data/outputs/example.json",
    "csv": "/data/outputs/example.csv",
    "pdf": "/data/outputs/example.pdf"
  }
}
```

---

## 3. Configuration

All configuration is via environment variables. See `.env.example` for a complete template.

### Core Settings

| Variable | Purpose | Default |
|----------|---------|---------|
| `TESSITURE_ENV` | Runtime environment label | `production` |
| `TESSITURE_HOST` | API bind host | `0.0.0.0` |
| `TESSITURE_PORT` | API port | `8000` |
| `TESSITURE_UPLOAD_DIR` | Upload file storage path | `/data/uploads` |
| `TESSITURE_OUTPUT_DIR` | Output artifact path | `/data/outputs` |
| `TESSITURE_FRONTEND_DIST` | Path to built frontend | `frontend/dist` |

### Upload Validation

| Variable | Purpose | Default |
|----------|---------|---------|
| `TESSITURE_UPLOAD_MAX_BYTES` | Max upload size | `26214400` (25 MB) |
| `TESSITURE_UPLOAD_EXTENSIONS` | Allowed file extensions | `.wav,.mp3,.flac,.m4a,.opus` |
| `TESSITURE_UPLOAD_MIME_TYPES` | Allowed MIME types | `audio/wav,audio/x-wav,audio/mpeg,audio/flac,audio/x-flac,audio/mp4,audio/opus,audio/x-opus,audio/ogg,application/ogg` |

### Analysis Tuning

| Variable | Purpose | Default |
|----------|---------|---------|
| `TESSITURE_TARGET_SAMPLE_RATE` | Target sample rate | `44100` |
| `TESSITURE_STFT_NFFT` | FFT window size | `4096` |
| `TESSITURE_STFT_HOP` | Hop length | `512` |
| `TESSITURE_BOOTSTRAP_SAMPLES` | Bootstrap replicate count | `1000` |
| `TESSITURE_BOOTSTRAP_CONFIDENCE_LEVEL` | CI confidence level | `0.95` |
| `TESSITURE_INFERENTIAL_PRESET` | Default null-hypothesis preset | `casual` |

### Rate Limiting

| Variable | Purpose | Default |
|----------|---------|---------|
| `TESSITURE_RATE_LIMIT_CAPACITY` | Token bucket capacity | `10` |
| `TESSITURE_RATE_LIMIT_REFILL_PER_SEC` | Refill rate (tokens/sec) | `0.5` |

### CORS

| Variable | Purpose | Default |
|----------|---------|---------|
| `TESSITURE_CORS_ORIGINS` | Comma-separated CORS allowlist | `http://localhost,http://127.0.0.1` |

### Frontend

| Variable | Purpose | Default |
|----------|---------|---------|
| `VITE_API_BASE_URL` | Absolute API base URL for frontend | empty (uses relative paths) |
| `VITE_API_PROXY_TARGET` | Vite dev server proxy target | `http://127.0.0.1:8000` |

---

## 4. Rate Limiting

The API uses a **token bucket** rate limiter per client IP address.

- Each IP starts with `TESSITURE_RATE_LIMIT_CAPACITY` tokens (default 10).
- Tokens refill at `TESSITURE_RATE_LIMIT_REFILL_PER_SEC` (default 0.5/sec).
- Each `POST /analyze` request consumes one token.
- When the bucket is empty, the API returns `429 Too Many Requests`.

---

## 5. Error Responses

| Status | Meaning |
|--------|---------|
| `404` | Job not found or requested artifact missing |
| `409` | Job exists but is not yet complete |
| `413` | Upload exceeds `TESSITURE_UPLOAD_MAX_BYTES` |
| `415` | Unsupported file extension or MIME type |
| `429` | Rate limit exceeded |
| `500` | Internal server error |

Error responses include a JSON body with a `detail` field:

```json
{ "detail": "Upload exceeds maximum size of 25 MB." }
```
