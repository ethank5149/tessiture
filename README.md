# Tessiture — Vocal Analysis Toolkit

Tessiture is a browser-based vocal analysis toolkit for analyzing acoustic recordings with statistically quantified uncertainty. Upload an audio file and get pitch trajectories, chord/key detection, tessitura metrics, vibrato analysis, formant estimates, and exportable reports — or compare your live voice against a reference track in real time.

**Production URL:** [https://tess.indecisivephysicist.space](https://tess.indecisivephysicist.space)

**Architecture:** FastAPI backend + React/Vite frontend, deployed as a single Docker container on Unraid via Docker Compose.

---

## Table of Contents

1. [Features](#features)
2. [Quick Start](#quick-start)
3. [Development Workflow](#development-workflow)
4. [Development Environment (VSCode Dev Container)](#development-environment-vscode-dev-container)
5. [Build & Release](#build--release)
6. [Configuration](#configuration)
7. [Deployment](#deployment)
8. [Project Structure](#project-structure)
9. [Version Info](#version-info)
10. [Documentation](#documentation)

---

## Features

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

## Quick Start

### Prerequisites

- Python 3.12
- Node.js 20+
- `libsndfile`, `ffmpeg` (for audio processing)
- Docker + Docker Compose v2 (for deployment only)

### First-Time Setup

```bash
# 1. Copy and configure the environment file
cp deploy/.env.example deploy/.env
# Edit deploy/.env — set TESSITURE_IMAGE, host paths, CORS origins, etc.

# 2. Install Python dependencies (creates .venv/)
make install-dev

# 3. Install frontend dependencies
cd frontend && npm ci && cd ..
```

### Run Locally

```bash
# Start the FastAPI backend (http://0.0.0.0:8000)
make run-api

# In a separate terminal — start the Vite frontend dev server (http://0.0.0.0:5173)
make run-frontend
```

---

## Development Workflow

### Running Tests

```bash
# Backend pytest suite
make test

# Backend linting
make lint

# Code formatting
make format

# Type checking
make typecheck

# Frontend tests
cd frontend && npm run test
```

### Building the Frontend

```bash
# Build frontend assets (reads .release-version if present for version injection)
make build-frontend
```

---

## Development Environment (VSCode Dev Container)

Tessiture is developed from within a **VSCode Dev Container** running on the Unraid host. The workspace (`/mnt/user/public/tessiture`) is bind-mounted into the container, so all `make` commands — including `make release` — work from inside the container as long as the container is configured correctly.

### Requirements

The dev container needs three things to support the full build/deploy workflow:

| Requirement | Why |
|-------------|-----|
| Docker socket mounted (`/var/run/docker.sock`) | `build.sh` and `one-shot.sh` call `docker build` and `docker compose` against the host daemon |
| Docker CLI installed inside the container | The CLI binary must be present; the daemon itself runs on the Unraid host |
| Git installed inside the container | `build.sh` reads commit history for `auto` version bumping and creates annotated git tags |

### Minimal `.devcontainer/devcontainer.json`

Create `.devcontainer/devcontainer.json` in the repository root with at minimum the Docker socket mount:

```json
{
  "name": "Tessiture Dev",
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
  "mounts": [
    "source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"
  ],
  "postCreateCommand": "apt-get update && apt-get install -y docker.io git",
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "charliermarsh.ruff",
        "esbenp.prettier-vscode"
      ]
    }
  }
}
```

> **Note:** The `.devcontainer/` directory does not exist in the repository by default. Create it when setting up your dev container environment.

### Host Paths in `deploy/.env`

The variables `TESSITURE_UPLOAD_HOST_PATH`, `TESSITURE_OUTPUT_HOST_PATH`, `TESSITURE_JOBS_HOST_PATH`, `TESSITURE_LOG_HOST_PATH`, and `TESSITURE_STEM_CACHE_HOST_PATH` must be **Unraid host absolute paths** (e.g., `/mnt/user/appdata/tessiture/uploads`), not paths inside the dev container.

When `deploy.sh` creates these directories and Docker mounts them into the Tessiture container, it does so via the host Docker daemon — so the paths are resolved on the Unraid host filesystem, not inside the dev container.

### What Happens When You Run `make release` from Inside the Container

1. `make release` calls `deploy/scripts/one-shot.sh`
2. `one-shot.sh` detects it is running inside a container (`/.dockerenv` present) and logs `Docker preflight: context=container`
3. It verifies `/var/run/docker.sock` is mounted — if missing, it exits with a clear error (see Troubleshooting below)
4. `docker build` executes against the **host's Docker daemon** — the resulting image appears on the Unraid host
5. Git operations (`git log`, `git tag`) run inside the dev container against the bind-mounted `.git/` directory — tags are written to the repo's git history
6. `docker compose up` deploys the Tessiture container on the **Unraid host** — the running container is visible in Unraid's Docker tab

### Troubleshooting

**"Docker socket /var/run/docker.sock is not available in this container"**

The Docker socket is not mounted into the dev container. Add the socket mount to `.devcontainer/devcontainer.json` (see example above) and rebuild the container.

**"Docker CLI is missing in this container"**

Install the Docker CLI inside the container:
```bash
apt-get update && apt-get install -y docker.io
```

**Permission denied on `/var/run/docker.sock`**

Add your user to the `docker` group inside the container, or prefix Docker commands with `sudo`. The socket is owned by the `docker` group on the host; the group ID must match inside the container.

---

## Build & Release

The primary release interface is the `Makefile`. All build, versioning, and deployment operations are driven through `make` targets backed by scripts in [`deploy/scripts/`](deploy/scripts/).

### Primary Release Command

```bash
# Full release: build Docker image → deploy compose stack → verify health
make release
```

### Versioning

Tessiture uses **semantic versioning** (`MAJOR.MINOR.PATCH`). The default strategy is `VERSION_BUMP=auto`, which scans git commit subjects since the last `v*.*.*` tag:

| Commit pattern | Bump |
|----------------|------|
| Subject contains `BREAKING CHANGE`, or uses `type!:` / `type(scope)!:` format | **major** |
| Subject starts with `feat:` or `feat(scope):` | **minor** |
| All other commits | **patch** |

After a successful build, [`deploy/scripts/build.sh`](deploy/scripts/build.sh) automatically:
1. Writes the new version to `.release-version` in the repo root
2. Updates `TESSITURE_IMAGE` in `deploy/.env` to the new versioned tag
3. Creates an annotated git tag `v{version}` (e.g., `v1.3.0`)

To push tags to remote after a build:
```bash
git push --tags
```

To skip git tagging (useful for CI):
```bash
make build NO_GIT_TAG=1
```

### Release Workflow

```bash
# Full release (build + deploy + verify) — most common
make release

# With an explicit version bump
make release VERSION_BUMP=minor

# Build only (no deploy)
make build

# Build and push to a registry
make build-push IMAGE=ghcr.io/yourorg/tessiture

# Deploy only (uses already-built image from deploy/.env)
make deploy
```

### All Makefile Targets

| Target | Description |
|--------|-------------|
| `make help` | Show all targets (default) |
| `make install` | Install Python runtime deps into `.venv/` |
| `make install-dev` | Install Python runtime + dev deps into `.venv/` |
| `make test` | Run pytest |
| `make lint` | Run ruff lint checks |
| `make format` | Run black formatting |
| `make typecheck` | Run mypy type checks |
| `make run-api` | Start uvicorn dev server |
| `make run-frontend` | Start Vite frontend dev server |
| `make build-frontend` | Build frontend assets (injects version from `.release-version`) |
| `make build` | Build Docker image with semver bump |
| `make build-push` | Build and push image to registry |
| `make deploy` | Deploy compose stack |
| `make release` | **Full release: build → deploy → verify** (primary command) |
| `make tag` | Re-tag current version in git without rebuilding |
| `make clean` | Remove build artifacts |

> **Deprecated aliases** (still functional): `unraid-build`, `unraid-build-push`, `unraid-deploy`, `unraid-one-shot`

### Makefile Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `VERSION_BUMP` | `auto` | Version bump strategy: `auto\|patch\|minor\|major\|none` |
| `BASE_VERSION` | `0.0.0` | Fallback version when image tag is not semver |
| `IMAGE` | _(from `deploy/.env`)_ | Override Docker image repo/tag |
| `ENV_FILE` | `deploy/.env` | Path to environment file |
| `COMPOSE_FILE` | `deploy/docker-compose.yml` | Path to compose file |
| `NO_GIT_TAG` | _(unset)_ | Set to `1` to skip git tagging |

---

## Configuration

Runtime configuration lives in `deploy/.env` (copied from [`deploy/.env.example`](deploy/.env.example)). This file is the single source of truth for all deployment settings.

| Variable | Default | Purpose |
|----------|---------|---------|
| `TESSITURE_IMAGE` | `ghcr.io/your-org/tessiture:latest` | Docker image tag (auto-updated by `build.sh`) |
| `TESSITURE_PORT` | `8000` | Internal container port |
| `TESSITURE_LAN_BIND_PORT` | `8000` | Host loopback bind port |
| `TESSITURE_UPLOAD_HOST_PATH` | `/mnt/user/appdata/tessiture/uploads` | Host path for uploaded audio files |
| `TESSITURE_OUTPUT_HOST_PATH` | `/mnt/user/appdata/tessiture/outputs` | Host path for analysis outputs |
| `TESSITURE_JOBS_HOST_PATH` | `/mnt/user/appdata/tessiture/jobs` | Host path for job state |
| `TESSITURE_LOG_HOST_PATH` | `/mnt/user/appdata/tessiture/logs` | Host path for logs |
| `TESSITURE_PUBLIC_HOSTNAME` | `tess.indecisivephysicist.space` | Public hostname (used for CORS) |
| `TESSITURE_CORS_ORIGINS` | _(your origin)_ | Allowed CORS origins, comma-separated |
| `TESSITURE_UPLOAD_MAX_BYTES` | `26214400` | Max upload size in bytes (25 MB) |
| `TESSITURE_RATE_LIMIT_CAPACITY` | `10` | Token bucket capacity for rate limiting |
| `TESSITURE_RATE_LIMIT_REFILL_PER_SEC` | `0.5` | Token bucket refill rate |
| `TESSITURE_VOCAL_SEPARATION` | `auto` | Vocal separation mode: `auto\|disabled` |
| `TESSITURE_STEM_CACHE_HOST_PATH` | `/mnt/user/appdata/tessiture/stem_cache` | Host path for Demucs stem cache |
| `TESSITURE_RELEASE_VERSION` | _(set by `one-shot.sh`)_ | Semantic version injected at deploy time |

All four host data paths (`UPLOAD`, `OUTPUT`, `JOBS`, `LOG`) are automatically created by [`deploy/scripts/deploy.sh`](deploy/scripts/deploy.sh) if they do not exist.

---

## Deployment

Tessiture deploys as a single Docker container on an Unraid host using Docker Compose. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full deployment reference.

### Networking

- The container binds to `127.0.0.1:{TESSITURE_LAN_BIND_PORT}` (loopback only — not exposed on LAN)
- The container also joins the `caddy_proxy` Docker network (must pre-exist) for reverse proxy routing via Caddy
- Caddy configuration lives **outside** the repository at `/mnt/user/appdata/caddy/Caddyfile`

### Deploy Files

```
deploy/
  .env.example          # Configuration template — copy to deploy/.env
  docker-compose.yml    # Compose service definition
  scripts/
    build.sh            # Build Docker image, compute semver, write git tag
    deploy.sh           # docker compose up (creates host paths if missing)
    one-shot.sh         # Orchestrates: build → deploy → verify
```

---

## Project Structure

```
analysis/      DSP, pitch, chords, tessitura, advanced voice analysis
api/           FastAPI server, routes, job management, streaming
calibration/   Confidence models and Monte Carlo utilities
reporting/     JSON, CSV, and PDF report generation
frontend/      React + Vite client application
docs/          Architecture, math, API, and deployment documentation
tests/         Backend test suites (pytest)
deploy/        Docker Compose stack, env template, and release scripts
plans/         Design plans and archived roadmap documents
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
| **[Deployment](docs/DEPLOYMENT.md)** | Full deployment reference: build system, versioning, Caddy, Unraid, troubleshooting |
| **[Architecture](docs/ARCHITECTURE.md)** | Technical reference: analysis pipeline, calibration, comparison, frontend, design decisions |
| **[API Reference](docs/API_REFERENCE.md)** | Endpoints, result JSON schema, configuration variables |
| **[Mathematical Foundations](docs/MATHEMATICAL_FOUNDATIONS.md)** | Proofs, derivations, uncertainty formulas, and bibliography |
| **[Agent Rules](AGENTS.md)** | Operational rules for AI/code agents working in this repository |
