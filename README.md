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
- Linux audio runtime dependencies: `libsndfile` and `ffmpeg` (`ffmpeg` is required for reliable Opus decoding in containerized deployments and is installed automatically in Docker)

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
- **Accepted extensions** (default): `.wav`, `.mp3`, `.flac`, `.m4a`, `.opus`
- **Accepted MIME types** (default):
  `audio/wav`, `audio/x-wav`, `audio/mpeg`, `audio/flac`, `audio/x-flac`, `audio/mp4`, `audio/opus`, `audio/x-opus`, `audio/ogg`, `application/ogg`

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
| `TESSITURE_UPLOAD_EXTENSIONS` | Allowed file extensions | `.wav,.mp3,.flac,.m4a,.opus` |
| `TESSITURE_UPLOAD_MIME_TYPES` | Allowed MIME list | `audio/wav,audio/x-wav,audio/mpeg,audio/flac,audio/x-flac,audio/mp4,audio/opus,audio/x-opus,audio/ogg,application/ogg` |
| `TESSITURE_RATE_LIMIT_CAPACITY` | Token bucket capacity | `10` |
| `TESSITURE_RATE_LIMIT_REFILL_PER_SEC` | Refill rate (tokens/sec) | `0.5` |
| `TESSITURE_CORS_ORIGINS` | Comma-separated CORS allowlist | `http://localhost,http://127.0.0.1` |
| `VITE_API_BASE_URL` | Frontend absolute API base URL | empty |

For operators, keep upload validation variables aligned with [` .env.example`](.env.example):

```bash
TESSITURE_UPLOAD_EXTENSIONS=.wav,.mp3,.flac,.m4a,.opus
TESSITURE_UPLOAD_MIME_TYPES=audio/wav,audio/x-wav,audio/mpeg,audio/flac,audio/x-flac,audio/mp4,audio/opus,audio/x-opus,audio/ogg,application/ogg
```

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

### Recommended internet topology (production)

```text
Internet -> Cloudflare Tunnel (externally managed/shared cloudflared) -> Tessiture API container
```

- This repository's Unraid stack deploys **Tessiture only**.
- **Cloudflare Tunnel is external/shared and is not deployed by this stack.**
- **Caddy is optional and LAN-only** (local reverse proxy/debug path), and is **not** part of the internet ingress path.

### Unraid stack files (in this repo)

- Compose stack: `deploy/unraid/docker-compose.yml`
- Env template: `deploy/unraid/.env.unraid.example`

### Opus decoding requirement (containers)

- Container images must include `ffmpeg` for reliable Opus decoding at runtime.
- The project Docker image already installs `ffmpeg` and `libsndfile1`.
- If Opus decode support is unavailable at runtime, `POST /analyze` fails with an explicit dependency error message.

### Unraid maintenance helpers (repo root)

These scripts provide repeatable one-shot maintenance flows for build/deploy operations.

1) Create runtime env file once:

```bash
cp deploy/unraid/.env.unraid.example deploy/unraid/.env.unraid
```

2) Edit `deploy/unraid/.env.unraid` and set at minimum:

- `TESSITURE_IMAGE`
- `TESSITURE_CORS_ORIGINS`
- `TESSITURE_UPLOAD_HOST_PATH`
- `TESSITURE_OUTPUT_HOST_PATH`

3) Run helpers:

```bash
# Build local-only image (default: tessiture:local)
bash deploy/unraid/scripts/build.sh

# Build a specific tag (optional push)
bash deploy/unraid/scripts/build.sh --image ghcr.io/your-org/tessiture:latest --push

# Deploy stack with deploy/unraid/.env.unraid
bash deploy/unraid/scripts/deploy.sh

# One-shot: build + deploy + health verification
bash deploy/unraid/scripts/one-shot.sh
```

Optional Make targets:

```bash
make unraid-build
make unraid-deploy
make unraid-one-shot
# push flow (requires IMAGE value)
make unraid-build-push IMAGE=ghcr.io/your-org/tessiture:latest
```

`deploy.sh` always reads `TESSITURE_IMAGE` from `deploy/unraid/.env.unraid` for deployment. `one-shot.sh` enforces the same image alignment to avoid drift between build and deploy.

This stack provides:

- Tessiture service (no bundled cloudflared service)
- Restart policy (`unless-stopped`)
- App healthcheck
- Internal named Docker network (`tessiture_internal`)
- Persistent Unraid host mounts for uploads/outputs
- Env-file-driven configuration
- Optional/commented host port mapping for LAN debug only

### Deploy on Unraid (copy/paste flow)

1) Build and publish the Tessiture image from this repository (or reuse an existing published tag).

2) On Unraid, create a folder for the stack and copy both deployment files there.

3) Create the runtime env file:

```bash
cp .env.unraid.example .env.unraid
```

4) Edit `.env.unraid` and set at minimum:

- `TESSITURE_IMAGE`
- `TESSITURE_CORS_ORIGINS`
- `TESSITURE_UPLOAD_HOST_PATH`
- `TESSITURE_OUTPUT_HOST_PATH`

5) Start the stack:

```bash
docker compose -f docker-compose.yml --env-file .env.unraid up -d
```

### Configure existing shared Cloudflare Tunnel ingress (external)

1. In your existing/shared Cloudflare Tunnel setup, route the Tessiture hostname to:
   - `http://tessiture:8000`
2. Ensure the shared `cloudflared` container is attached to the `tessiture_internal` Docker network created by this stack so the `tessiture` service name resolves.
3. Keep Caddy out of the internet path (LAN-only usage).

Example ingress rule (existing tunnel config):

```yaml
ingress:
  - hostname: voice.example.com
    service: http://tessiture:8000
  - service: http_status:404
```

### Migration / cutover runbook

#### 1) Parallel route test (no DNS cutover yet)

1. In your existing/shared Cloudflare Tunnel, add a temporary public hostname targeting Tessiture at `http://tessiture:8000`.
2. Keep your existing production route active.
3. Validate temporary hostname:
   - `POST /analyze` returns job id
   - `GET /status/{job_id}` reaches `completed`
   - `GET /results/{job_id}?format=json|csv|pdf` returns expected artifacts

#### 2) Cutover

1. Update the primary public hostname route in the existing/shared tunnel to `http://tessiture:8000`.
2. Keep TTL low during change window if applicable.
3. Confirm active traffic uses the new route and analysis jobs complete successfully.

#### 3) Rollback

1. Re-point the Cloudflare public hostname back to the prior origin/service in the shared tunnel configuration.
2. If needed, stop the new stack:

```bash
docker compose -f docker-compose.yml --env-file .env.unraid down
```

3. Confirm old route serves traffic normally.

#### 4) Validation checklist

- [ ] `docker ps` shows `tessiture` healthy/running
- [ ] Shared `cloudflared` container remains healthy/running outside this stack
- [ ] Shared tunnel ingress points to `http://tessiture:8000`
- [ ] Uploads write to configured Unraid uploads path
- [ ] JSON/CSV/PDF outputs write to configured Unraid outputs path
- [ ] Browser/API clients succeed from allowed CORS origins
- [ ] Rate limiting and max upload settings match expected policy
- [ ] No internet traffic is routed through Caddy in the recommended production flow

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
| v0.x | **Ash** | Experimental development releases using synthetic reference datasets and uncertainty calibration workflows. |
| v1.x | **Tessa** | First official release line with calibrated real-world evaluation workflows. |

---

## Dataset Conventions

Dataset identifiers represent semantic roles rather than fixed file names.

- `REFERENCE_DATASET`: calibration data with known ground truth
- `TESSA_DATASET`: real-world evaluation data

These roles stay distinct even when a temporary implementation maps each role to a single concrete dataset.