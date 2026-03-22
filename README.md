# Tessiture — Vocal Analysis Toolkit

Tessiture is a browser-based vocal analysis toolkit for analyzing acoustic recordings with statistically quantified uncertainty. Upload an audio file and get pitch trajectories, chord/key detection, tessitura metrics, vibrato analysis, formant estimates, and exportable reports — or compare your live voice against a reference track in real time.

**Production URL:** [https://tess.indecisivephysicist.space](https://tess.indecisivephysicist.space)

**Architecture:** FastAPI backend + React/Vite frontend

---

## Current Features

1. **Pitch Analysis** — Fundamental frequency estimation, MIDI conversion, path optimization
2. **Chord & Key Detection** — Using pitch class histograms, tonal profiles, Viterbi smoothing
3. **Tessitura Analysis** — Vocal range detection, voice type classification
4. **Vibrato Analysis** — Rate and extent extraction
5. **Formant Analysis** — Formant frequency estimation
6. **Phrase Segmentation** — Automatic phrase boundary detection
7. **Vocal Separation** — Stem separation using Demucs
8. **Reference Comparison** — Compare recordings against reference tracks
9. **Live Comparison** — Real-time microphone analysis via WebSocket
10. **Spectrogram Inspector** — Interactive frequency-time visualization
11. **Calibration & Uncertainty** — Monte Carlo confidence intervals
12. **Report Export** — JSON, CSV, and PDF report generation
13. **Example Gallery** — Pre-loaded example tracks

---

## Quick Start (Local Development)

### Prerequisites

- Python 3.11+
- Node.js 20+
- libsndfile
- ffmpeg

### Install & Run

```bash
# Install all dependencies
make install-dev

# Start backend API (http://0.0.0.0:8000)
make run-api

# In another terminal — start frontend dev server (http://0.0.0.0:5173)
make run-frontend
```

---

## Testing

```bash
# Backend pytest suite
make test

# Backend linting and type checking
make lint
make format
make typecheck

# Frontend tests
cd frontend && npm run test:run
```

---

## Build Commands

```bash
# Production frontend build
make build-frontend

# Single-image Docker container
make docker-build
```

---

## Deployment (Unraid)

```bash
# Build with auto semver bump
make unraid-build

# Build and push to registry
make unraid-build-push

# Deploy compose stack
make unraid-deploy

# Build + deploy + verify (one-shot)
make unraid-one-shot
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TESSITURE_IMAGE` | Docker image (e.g., `ghcr.io/your-org/tessiture:latest`) |
| `TESSITURE_PORT` | Backend port (default: 8000) |
| `TESSITURE_PUBLIC_HOSTNAME` | Production hostname (e.g., `tess.indecisivephysicist.space`) |
| `TESSITURE_UPLOAD_DIR` | Upload directory in container |
| `TESSITURE_OUTPUT_DIR` | Output directory in container |
| `TESSITURE_EXAMPLES_DIR` | Example tracks directory |
| `TESSITURE_JOBS_DIR` | Job queue directory |
| `TESSITURE_LOG_DIR` | Log directory |
| `TESSITURE_UPLOAD_MAX_BYTES` | Max upload size (default: 26214400) |
| `TESSITURE_RATE_LIMIT_CAPACITY` | Rate limit capacity |
| `TESSITURE_RATE_LIMIT_REFILL_PER_SEC` | Rate limit refill rate |
| `TESSITURE_CORS_ORIGins` | Allowed CORS origins |
| `TESSITURE_VOCAL_SEPARATION` | Vocal separation mode (`auto`, `disabled`) |

Host path overrides for persistent storage:
- `TESSITURE_UPLOAD_HOST_PATH`
- `TESSITURE_OUTPUT_HOST_PATH`
- `TESSITURE_JOBS_HOST_PATH`
- `TESSITURE_LOG_HOST_PATH`
- `TESSITURE_STEM_CACHE_HOST_PATH`

---

## Project Structure

```
analysis/      DSP, pitch, chords, tessitura, advanced voice analysis
api/           FastAPI server, routes, job management
calibration/   Confidence and Monte Carlo utilities
reporting/     JSON/CSV/PDF report generation
frontend/      React + Vite client
docs/          Architecture, math, API, deployment docs
tests/         Backend and frontend test suites
deploy/        Unraid deployment scripts
```

---

## Version Info

Semantic versioning (`MAJOR.MINOR.PATCH`).

| Version | Codename | Description |
|---------|----------|-------------|
| v0.x | **Ash** | Experimental development releases |
| v1.x | **Tessa** | First official release line |

---

## Documentation

| Document | Description |
|----------|-------------|
| **[Architecture](docs/ARCHITECTURE.md)** | Full technical reference: analysis pipeline, calibration, comparison, frontend, design decisions |
| **[Mathematical Foundations](docs/MATHEMATICAL_FOUNDATIONS.md)** | All proofs, derivations, uncertainty formulas, and bibliography |
| **[API Reference](docs/API_REFERENCE.md)** | Endpoints, result JSON schema, configuration variables |
| **[Deployment](docs/DEPLOYMENT.md)** | Docker builds, Unraid compose, Cloudflare Tunnel, deployment checklist |
| **[Agent Rules](AGENTS.md)** | Operational rules for AI/code agents working in this repository |
