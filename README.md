# Tessiture — Vocal Analysis Toolkit

> Legacy status note: `tonescout/` is now read-only/maintenance-only and being archived; active development and new contributions should target `tessiture/`.

Tessiture is a browser-based toolkit for analyzing vocal and acoustic recordings with statistically quantified uncertainty. Upload an audio file and get pitch trajectories, chord/key detection, tessitura metrics, vibrato analysis, formant estimates, and exportable reports — or compare your live voice against a reference track in real time.

**Production:** [tess.indecisivephysicist.space](https://tess.indecisivephysicist.space)

---

## Documentation

| Document | Description |
|----------|-------------|
| **[Architecture](docs/ARCHITECTURE.md)** | Full technical reference: analysis pipeline, calibration, comparison, frontend, design decisions |
| **[Mathematical Foundations](docs/MATHEMATICAL_FOUNDATIONS.md)** | All proofs, derivations, uncertainty formulas, and bibliography |
| **[API Reference](docs/API_REFERENCE.md)** | Endpoints, result JSON schema, configuration variables |
| **[Deployment](docs/DEPLOYMENT.md)** | Docker builds, Unraid compose, Cloudflare Tunnel, deployment checklist |
| **[Agent Rules](AGENTS.md)** | Operational rules for AI/code agents working in this repository |

---

## Quick Start (Local Development)

### Prerequisites

- Python `>=3.11,<3.13`
- Node.js 20+ and npm
- `libsndfile` and `ffmpeg`

### Install & Run

```bash
# Install all dependencies
make install-dev

# Start backend API (http://0.0.0.0:8000)
make run-api

# In another terminal — start frontend dev server (http://0.0.0.0:5173)
make run-frontend
```

### Testing

```bash
# Backend
make test
make lint
make typecheck

# Frontend
cd frontend && npm run test:run
```

---

## How It Works

1. **Upload** audio via the web UI or `POST /analyze`
2. **Poll** job progress via `GET /status/{job_id}`
3. **Retrieve** results as JSON, CSV, or PDF via `GET /results/{job_id}`

For live comparison: connect to `WS /compare/live`, stream microphone audio, and receive real-time pitch feedback.

---

## Project Structure

```
analysis/      Core DSP, pitch, chords, tessitura, and advanced voice analysis
api/           FastAPI server, routes, and in-memory job management
calibration/   Confidence and Monte Carlo calibration utilities
reporting/     JSON/CSV/PDF report generation and visualization helpers
frontend/      React + Vite client application
docs/          Architecture, math, API, and deployment documentation
tests/         Backend and frontend test suites
deploy/        Unraid deployment scripts and compose files
plans/         Active planning docs and archived historical plans
```

---

## Versioning

Semantic versioning (`MAJOR.MINOR.PATCH`).

| Version | Codename | Description |
|---------|----------|-------------|
| v0.x | **Ash** | Experimental development releases |
| v1.x | **Tessa** | First official release line |

---

## Dataset Conventions

- `REFERENCE_DATASET` — calibration data with known ground truth
- `TESSA_DATASET` — real-world evaluation data