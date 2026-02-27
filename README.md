# Tessiture - Vocal Analysis Toolkit

Tessiture is a web-based toolkit for analyzing vocal and acoustic recordings with a practical, production-oriented pipeline.

It extracts musical and voice features such as:

- Pitch trajectories and note events
- Chord and key estimations
- Tessitura and vocal-range metrics
- Advanced voice features (vibrato, formants, phrase segmentation)
- Uncertainty summaries and exportable reports

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start (Local Development)](#quick-start-local-development)
- [API Endpoints](#api-endpoints)
- [Result Structure](#result-structure)
- [Configuration](#configuration)
- [Frontend Development Notes](#frontend-development-notes)
- [Testing and Quality Checks](#testing-and-quality-checks)
- [Docker and Unraid Deployment](#docker-and-unraid-deployment)
- [Project Structure](#project-structure)
- [Versioning and Codenames](#versioning-and-codenames)
- [Dataset Conventions](#dataset-conventions)

---

## Overview

Tessiture uses an asynchronous API workflow:

1. Upload audio via `POST /analyze`
2. Poll job state via `GET /status/{job_id}`
3. Retrieve results via `GET /results/{job_id}` in JSON, CSV, or PDF format

The backend processing pipeline combines DSP, pitch tracking, symbolic aggregation, and report generation.

---

## Architecture

### High-level flow

```text
Audio Upload
  -> Preprocessing (resample, mono conversion, normalization)
  -> STFT + harmonic peak analysis
  -> Pitch candidate estimation + lead-voice optimization
  -> MIDI/note conversion + note event segmentation
  -> Chord and key estimation
  -> Tessitura + advanced features (vibrato, formants, phrase boundaries)
  -> Uncertainty summary
  -> Report exports (JSON / CSV / PDF)
```

### Runtime components

- **API server**: FastAPI app with CORS and optional static frontend mount
- **Job execution**: in-memory async job manager (non-persistent)
- **Analysis modules**: `analysis/`, `calibration/`, and `reporting/` packages
- **Frontend**: React + Vite UI for upload, polling, visualization, and exports

---

## Quick Start (Local Development)

### 1) Prerequisites

- Python `>=3.11,<3.13`
- Node.js 20+ and npm
- Linux shared library `libsndfile` (required by audio stack; installed automatically in Docker)

### 2) Install dependencies

```bash
make install-dev
```

This installs runtime dependencies from `requirements.txt` plus development extras from `pyproject.toml`.

### 3) Run backend API

```bash
make run-api
```

The API starts on `http://0.0.0.0:8000` by default.

### 4) Run frontend

In another terminal:

```bash
make run-frontend
```

The frontend dev server starts on `http://0.0.0.0:5173`.

If `VITE_API_BASE_URL` is empty, the frontend uses relative paths (`/analyze`, `/status`, `/results`) and relies on Vite proxy settings.

---

## API Endpoints

### `POST /analyze`

Uploads an audio file and schedules background analysis.

- **Multipart field**: `audio`
- **Accepted extensions** (default): `.wav`, `.mp3`, `.flac`, `.m4a`
- **Accepted MIME types** (default):
  `audio/wav`, `audio/x-wav`, `audio/mpeg`, `audio/flac`, `audio/x-flac`, `audio/mp4`

Response:

```json
{
  "job_id": "2d7e5c3b-...",
  "status_url": "/status/2d7e5c3b-...",
  "results_url": "/results/2d7e5c3b-..."
}
```

### `GET /status/{job_id}`

Returns job metadata and progress.

Response fields include:

- `job_id`
- `status` (`queued`, `processing`, `completed`, `failed`)
- `progress` (integer percent)
- `created_at`, `updated_at` (ISO8601)
- `result_path` (if available)
- `error` (traceback text when failed)

### `GET /results/{job_id}?format={json|csv|pdf}`

- `format=json`: returns full structured analysis payload
- `format=csv`: returns downloadable CSV file
- `format=pdf`: returns downloadable PDF file

Common error behaviors:

- `404`: job not found or requested artifact missing
- `409`: job exists but is not complete
- `429`: rate limit exceeded

---

## Result Structure

JSON results contain normalized sections:

- `metadata`
- `summary`
- `pitch` and `pitch_frames`
- `notes` and `note_events`
- `chords`
- `keys`
- `tessitura`
- `advanced` (vibrato, formants, phrase segmentation)
- `uncertainty`
- `files` (generated report paths)

Minimal example:

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
    "tessitura_range": [57.0, 69.0],
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
  "files": {
    "json": "/data/outputs/example.json",
    "csv": "/data/outputs/example.csv",
    "pdf": "/data/outputs/example.pdf"
  }
}
```

---

## Configuration

Primary environment variables (see `.env.example`):

| Variable | Purpose | Default |
|---|---|---|
| `TESSITURE_ENV` | Runtime environment label | `production` |
| `TESSITURE_HOST` | API bind host | `0.0.0.0` |
| `TESSITURE_PORT` | API port | `8000` |
| `TESSITURE_UPLOAD_DIR` | Upload file storage path | `/data/uploads` |
| `TESSITURE_OUTPUT_DIR` | Output artifact path | `/data/outputs` |
| `TESSITURE_UPLOAD_MAX_BYTES` | Max upload size in bytes | `26214400` |
| `TESSITURE_UPLOAD_EXTENSIONS` | Allowed file extensions | `.wav,.mp3,.flac,.m4a` |
| `TESSITURE_UPLOAD_MIME_TYPES` | Allowed MIME list | audio mime list |
| `TESSITURE_RATE_LIMIT_CAPACITY` | Token bucket capacity | `10` |
| `TESSITURE_RATE_LIMIT_REFILL_PER_SEC` | Refill rate (tokens/sec) | `0.5` |
| `TESSITURE_CORS_ORIGINS` | Comma-separated CORS allowlist | `http://localhost,http://127.0.0.1` |
| `VITE_API_BASE_URL` | Frontend absolute API base URL | empty |

Additional backend tuning variables are also supported:

- `TESSITURE_TARGET_SAMPLE_RATE` (default `44100`)
- `TESSITURE_STFT_NFFT` (default `4096`)
- `TESSITURE_STFT_HOP` (default `512`)
- `TESSITURE_FRONTEND_DIST` (default `frontend/dist`)

---

## Frontend Development Notes

- Vite dev server proxies `/analyze`, `/status`, and `/results`.
- Proxy target uses `VITE_API_PROXY_TARGET` and defaults to `http://127.0.0.1:8000`.
- Frontend API client normalizes response shape so components can rely on stable fields.

Useful scripts (from `frontend/package.json`):

```bash
npm run dev
npm run build
npm run preview
npm run test
npm run test:run
```

---

## Testing and Quality Checks

Backend (repo root):

```bash
make test
make lint
make format
make typecheck
```

Frontend tests:

```bash
cd frontend
npm run test:run
```

Current tests cover:

- Core analysis computations (DSP, pitch, chords, tessitura, advanced features)
- API submission/status/results flow
- Reporting generator output contracts
- Frontend component rendering and interaction states

---

## Docker and Unraid Deployment

Build image:

```bash
make docker-build
```

Run with Unraid-style bind mounts:

```bash
make docker-run-unraid
```

The container serves the API and, when built assets exist, statically serves `frontend/dist` from `/`.

---

## Project Structure

```text
analysis/      Core DSP, pitch, chords, tessitura, and advanced voice analysis
api/           FastAPI server, routes, and in-memory job management
calibration/   Confidence and Monte Carlo calibration utilities
reporting/     JSON/CSV/PDF report generation and visualization helpers
frontend/      React + Vite client application
tests/         Backend and frontend-focused tests
plans/         Roadmaps, scientific notes, and implementation plans
```

---

## Versioning and Codenames

Tessiture releases use semantic versioning (`MAJOR.MINOR.PATCH`).

| Version | Codename | Description |
|---|---|---|
| v0.x | **Synth** | Experimental development releases using synthetic reference datasets and uncertainty calibration workflows. |
| v1.x | **Tessa** | First official release line with calibrated real-world evaluation workflows. |

---

## Dataset Conventions

Dataset identifiers represent semantic roles rather than fixed file names.

- `REFERENCE_DATASET`: calibration data with known ground truth
- `TESSA_DATASET`: real-world evaluation data

These roles stay distinct even when a temporary implementation maps each role to a single concrete dataset.