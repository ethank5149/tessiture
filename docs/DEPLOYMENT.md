# Tessiture — Deployment Reference

**Last updated:** 2026-03-22

This document is the definitive reference for building, configuring, and deploying Tessiture on Unraid. It covers the build system, versioning strategy, environment configuration, networking, and day-to-day release workflow.

For API configuration variables, see [API_REFERENCE.md](API_REFERENCE.md).
For system architecture, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Table of Contents

1. [Deployment Overview](#1-deployment-overview)
2. [Prerequisites](#2-prerequisites)
3. [Development from a VSCode Dev Container](#3-development-from-a-vscode-dev-container)
4. [CI/CD with Forgejo Actions](#4-cicd-with-forgejo-actions)
5. [First-Time Setup](#5-first-time-setup)
6. [Environment File Reference](#6-environment-file-reference)
7. [Build System](#7-build-system)
8. [Deploy Script](#8-deploy-script)
9. [One-Shot Script (Primary Release)](#9-one-shot-script-primary-release)
10. [Makefile Reference](#10-makefile-reference)
11. [Networking](#11-networking)
12. [Updating / Re-deploying](#12-updating--re-deploying)
13. [Deployment Checklist](#13-deployment-checklist)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Deployment Overview

```
Internet → Cloudflare Tunnel (external/shared cloudflared on Unraid host)
         → 127.0.0.1:{TESSITURE_LAN_BIND_PORT}  (host loopback)
         → Tessiture container :8000

LAN      → Caddy reverse proxy (caddy_proxy Docker network)
         → Tessiture container :8000
```

**Key design points:**

- This repository deploys **Tessiture only** — one container, one compose stack.
- **Cloudflare Tunnel** is external and shared; it is not managed by this stack. Point your existing tunnel ingress at `http://127.0.0.1:{TESSITURE_LAN_BIND_PORT}` (host-network cloudflared) or at the container via the `caddy_proxy` network.
- **Caddy** is the LAN reverse proxy. It reaches Tessiture via the shared `caddy_proxy` Docker network. The Caddyfile lives **outside** this repository at `/mnt/user/appdata/caddy/Caddyfile`.
- The container also binds to `127.0.0.1:{TESSITURE_LAN_BIND_PORT}` on the host loopback so host-network processes (e.g., cloudflared) can reach it without joining the Docker network.

### WebSocket Support

Caddy passes WebSocket `Upgrade` and `Connection` headers transparently by default. The existing Caddyfile configuration does not strip these headers, so WebSocket connections to `WS /compare/live` work without additional proxy configuration.

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Docker Engine | Must be running on the Unraid host |
| Docker Compose v2 | `docker compose` (plugin, not `docker-compose`) |
| Nvidia GPU (optional) | Required only for GPU-accelerated vocal separation via Demucs |
| `caddy_proxy` Docker network | Must pre-exist; created by your Caddy stack |
| Git | Required for automatic version tagging |

The project [`Dockerfile`](../Dockerfile) installs `ffmpeg` and `libsndfile1` inside the image — no host-level audio library installation is needed for the container.

---

## 3. Development from a VSCode Dev Container

Tessiture is developed from within a **VSCode Dev Container** running on the Unraid host. The workspace (`/mnt/user/public/tessiture`) is bind-mounted into the container, giving the container full access to the source tree, `.git/` history, and `deploy/` scripts. All `make` targets — including `make release` — work from inside the container when the container is configured correctly.

Two dev container configurations are supported:

| | Option A: Socket Mount | Option B: Docker-in-Docker (DinD) |
|---|---|---|
| Docker daemon | Host's daemon | Separate daemon inside container |
| Built images | Appear on Unraid host | Isolated inside dev container |
| Deployed containers | Run on Unraid host | Run inside dev container (isolated) |
| Host path mounts in compose | Work correctly | **Do NOT work** — paths are inside DinD, not on Unraid host |
| Privileged mode required | No | Yes (handled by devcontainers feature) |
| `make deploy` / `make release` | ✅ Deploys to Unraid host | ❌ Does NOT deploy to Unraid host |
| Use case | Production deployment workflow | Local dev and testing only |

### Option A: Docker Socket Mount (Required for Production Deployment)

The dev container mounts the host's Docker socket (`/var/run/docker.sock`). All Docker operations — `docker build`, `docker compose up` — execute against the **host Docker daemon**, so built images and running containers appear on the Unraid host.

#### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Developer machine (or Unraid browser)                          │
│                                                                 │
│   VSCode ──────────────────────────────────────────────────┐   │
│                                                            │   │
└────────────────────────────────────────────────────────────┼───┘
                                                             │ SSH / Dev Containers extension
                                                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Unraid host                                                    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Dev Container (Docker)                                  │  │
│  │                                                          │  │
│  │  /mnt/user/public/tessiture  ◄── bind mount             │  │
│  │  /var/run/docker.sock        ◄── bind mount             │  │
│  │                                                          │  │
│  │  $ make release                                          │  │
│  │      └─► build.sh ──► docker build ──────────────────┐  │  │
│  │      └─► deploy.sh ─► docker compose up ──────────┐  │  │  │
│  └──────────────────────────────────────────────────┼──┼──┘  │
│                                                      │  │      │
│  Host Docker daemon ◄────────────────────────────────┘  │      │
│      └─► Tessiture image (built here)                   │      │
│      └─► Tessiture container (running here) ◄───────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

All Docker operations (`docker build`, `docker compose up`, directory creation) execute against the **host Docker daemon** via the socket. The resulting image and running container appear on the Unraid host — not inside the dev container.

#### Dev Container Requirements

| Requirement | Details |
|-------------|---------|
| **Docker socket bind mount** | `/var/run/docker.sock` must be mounted into the dev container. Without it, `build.sh` exits with: _"Docker socket /var/run/docker.sock is not available in this container."_ |
| **Docker CLI** | The `docker` binary must be installed inside the container (not Docker Engine — just the CLI client). Install with `apt-get install -y docker.io` or the [official Docker CLI install script](https://docs.docker.com/engine/install/). |
| **Git** | Required for `detect_auto_bump()` (reads `git log` since last `v*.*.*` tag) and `git_tag_release()` (creates annotated tag). Install with `apt-get install -y git`. |
| **Python 3.12 + venv** | Required for `make install-dev`, `make test`, `make run-api`. The `.venv/` directory is created inside the bind-mounted workspace. |
| **Node.js 20+** | Required for `make run-frontend`, `make build-frontend`, and frontend tests. |

#### Example `.devcontainer/devcontainer.json`

Create `.devcontainer/devcontainer.json` in the repository root:

```json
{
  "name": "Tessiture Dev",
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
  "mounts": [
    "source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"
  ],
  "postCreateCommand": "apt-get update && apt-get install -y docker.io git python3.12 python3.12-venv nodejs npm",
  "remoteUser": "vscode",
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "charliermarsh.ruff",
        "ms-azuretools.vscode-docker",
        "esbenp.prettier-vscode"
      ],
      "settings": {
        "python.defaultInterpreterPath": "/workspaces/tessiture/.venv/bin/python3.12"
      }
    }
  }
}
```

> **Note:** The `.devcontainer/` directory does not exist in the repository by default. Create it when setting up your dev container environment. Do not commit the Docker socket mount path if it is environment-specific.

#### Alternative: `.devcontainer/docker-compose.yml`

If you prefer a Docker Compose-based dev container, create `.devcontainer/docker-compose.yml`:

```yaml
version: "3.8"
services:
  dev:
    image: mcr.microsoft.com/devcontainers/base:ubuntu
    volumes:
      - ..:/workspaces/tessiture:cached
      - /var/run/docker.sock:/var/run/docker.sock
    command: sleep infinity
```

And reference it from `.devcontainer/devcontainer.json`:

```json
{
  "name": "Tessiture Dev",
  "dockerComposeFile": "docker-compose.yml",
  "service": "dev",
  "workspaceFolder": "/workspaces/tessiture"
}
```

#### `deploy/.env` Path Considerations

The host path variables in `deploy/.env` are resolved on the **Unraid host filesystem**, not inside the dev container. When `deploy.sh` auto-creates these directories and Docker bind-mounts them into the Tessiture container, it does so via the host Docker daemon.

| Variable | Must be... |
|----------|-----------|
| `TESSITURE_UPLOAD_HOST_PATH` | An absolute path on the Unraid host, e.g. `/mnt/user/appdata/tessiture/uploads` |
| `TESSITURE_OUTPUT_HOST_PATH` | An absolute path on the Unraid host, e.g. `/mnt/user/appdata/tessiture/outputs` |
| `TESSITURE_JOBS_HOST_PATH` | An absolute path on the Unraid host, e.g. `/mnt/user/appdata/tessiture/jobs` |
| `TESSITURE_LOG_HOST_PATH` | An absolute path on the Unraid host, e.g. `/mnt/user/appdata/tessiture/logs` |
| `TESSITURE_STEM_CACHE_HOST_PATH` | An absolute path on the Unraid host, e.g. `/mnt/user/appdata/tessiture/stem_cache` |

Do **not** use paths that are only valid inside the dev container (e.g., `/workspaces/tessiture/...`). Those paths do not exist on the host and the Tessiture container will fail to mount them.

#### Git Tagging from Inside the Container

Git operations work correctly from inside the dev container because the workspace — including `.git/` — is bind-mounted from the host. When `build.sh` runs `git tag -a v1.3.0 -m "Release v1.3.0"`, the tag is written to the repository's git history on the host filesystem. Push tags to your remote as usual:

```bash
git push --tags
```

#### `make release` Flow from Inside the Container

When you run `make release` from inside the dev container, the following sequence executes:

1. **`make release`** invokes `deploy/scripts/one-shot.sh` with the configured arguments
2. **Container detection** — `one-shot.sh` calls `is_container_runtime()`, detects `/.dockerenv`, and logs `Docker preflight: context=container`
3. **Socket check** — verifies `/var/run/docker.sock` is a socket; exits with a clear error if missing
4. **Docker CLI check** — verifies the `docker` binary is on `PATH`; exits with a clear error if missing
5. **Version bump** — reads `git log` since the last `v*.*.*` tag (runs inside the container against the bind-mounted `.git/`) and computes the next semver
6. **`docker build`** — executes against the host Docker daemon via the socket; the built image appears on the Unraid host
7. **`.release-version` written** — the resolved version string is written to the repo root (visible on the host via the bind mount)
8. **`TESSITURE_IMAGE` updated** — `deploy/.env` is updated in-place with the new versioned tag
9. **Git tag created** — `git tag -a v{version}` runs inside the container; the tag is written to the host-side `.git/`
10. **`docker compose up -d`** — deploys the Tessiture container on the Unraid host; the container is visible in Unraid's Docker tab
11. **Health verification** — polls the container's Docker healthcheck for up to 120 seconds

---

### Option B: Docker-in-Docker (DinD) — Local Dev/Test Only

DinD runs a **separate Docker daemon inside the dev container**. This provides a fully isolated Docker environment without requiring access to the host socket.

> ⚠️ **DinD is for local development and testing only.** `make deploy` and `make release` will create directories and run containers **inside the DinD container**, not on the Unraid host. The `*_HOST_PATH` variables in `deploy/.env` are resolved inside the DinD container's filesystem — they do not map to Unraid host paths. Use DinD to run `make test`, `make build`, and verify the image builds correctly. For production deployment, use Option A (socket mount).

#### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Unraid host                                                    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Dev Container (Docker, privileged)                      │  │
│  │                                                          │  │
│  │  /mnt/user/public/tessiture  ◄── bind mount             │  │
│  │                                                          │  │
│  │  DinD daemon (dockerd inside container)                  │  │
│  │      └─► docker build  ──► image (isolated here)        │  │
│  │      └─► docker compose up ──► container (isolated here)│  │
│  │                                                          │  │
│  │  $ make test   ✅  (runs pytest, npm test)               │  │
│  │  $ make build  ✅  (builds image inside DinD)            │  │
│  │  $ make deploy ❌  (deploys inside DinD, not Unraid)     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Host Docker daemon  (unaffected — DinD is isolated)           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### `.devcontainer/devcontainer.json` for DinD

```json
{
  "name": "Tessiture Dev (DinD)",
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
  "features": {
    "ghcr.io/devcontainers/features/docker-in-docker:2": {},
    "ghcr.io/devcontainers/features/python:1": { "version": "3.12" },
    "ghcr.io/devcontainers/features/node:1": { "version": "20" }
  },
  "postCreateCommand": "pip install -r requirements.txt && cd frontend && npm ci"
}
```

The `docker-in-docker` devcontainers feature starts a Docker daemon inside the container automatically and handles the required `--privileged` mode. No manual `runArgs` configuration is needed.

#### What Works with DinD

| Operation | Works? | Notes |
|-----------|--------|-------|
| `make test` | ✅ | Runs pytest and frontend tests |
| `make build` | ✅ | Builds Docker image (isolated inside DinD) |
| `make lint`, `make typecheck`, `make format` | ✅ | No Docker required |
| `make run-api`, `make run-frontend` | ✅ | Local dev servers |
| `make deploy` | ❌ | Deploys inside DinD, not on Unraid host |
| `make release` | ❌ | Same as above; host paths in `deploy/.env` do not exist inside DinD |
| Volume mounts using Unraid host paths | ❌ | Paths like `/mnt/user/appdata/...` do not exist inside DinD |

### Troubleshooting (Dev Container)

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Docker socket /var/run/docker.sock is not available in this container` | Socket not mounted (Option A) | Add `"source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"` to `mounts` in `devcontainer.json` and rebuild the container |
| `Docker CLI is missing in this container` | `docker` binary not installed | Run `apt-get update && apt-get install -y docker.io` inside the container, or add it to `postCreateCommand` |
| `permission denied while trying to connect to the Docker daemon socket` | Dev container user is not in the `docker` group | Run `sudo usermod -aG docker $USER` inside the container and restart, or prefix Docker commands with `sudo` |
| `git: command not found` | Git not installed in container | Run `apt-get install -y git` or add it to `postCreateCommand` |
| Host paths not found / Tessiture container fails to mount volumes | `deploy/.env` contains container-internal paths, or using DinD for deployment | Replace all `*_HOST_PATH` values with absolute Unraid host paths (e.g., `/mnt/user/appdata/tessiture/...`); use Option A (socket mount) for production deployment |
| `caddy_proxy` network not found | Network does not exist on the host | Run `docker network create caddy_proxy` on the host, or deploy your Caddy stack first |
| DinD: `make deploy` deploys inside container, not on Unraid | Using DinD for production deployment | Switch to Option A (socket mount) for production deployment |

---

## 4. CI/CD with Forgejo Actions

Tessiture includes two Forgejo Actions workflow files that automate testing and deployment via a self-hosted runner on the Unraid host.

### Overview

```
Developer pushes to main
        │
        ▼
Forgejo Actions (self-hosted runner on Unraid host)
        │
        ├─► test job: pytest + npm test + npm build
        │
        └─► build-and-deploy job (on success):
                │
                ├─► build.sh  ──► Docker image on Unraid host
                ├─► deploy.sh ──► Tessiture container on Unraid host
                ├─► health verification (120 s timeout)
                └─► git tag v{version} pushed back to Forgejo
```

| Workflow | File | Trigger | Jobs |
|----------|------|---------|------|
| **Test** | [`.forgejo/workflows/test.yml`](../.forgejo/workflows/test.yml) | Push to non-`main` branches; PRs targeting `main` | `test` only |
| **Release** | [`.forgejo/workflows/release.yml`](../.forgejo/workflows/release.yml) | Push to `main`; manual `workflow_dispatch` | `test` → `build-and-deploy` |

### Workflow Details

#### `test.yml` — Branch and PR Testing

Triggers on every push to a non-`main` branch and on every pull request targeting `main`. Runs the full test suite:

1. Checkout with `fetch-depth: 0` (full history)
2. Set up Python 3.12 → `pip install -r requirements.txt` → `python -m pytest tests/ -q --tb=short`
3. Set up Node.js 20 → `cd frontend && npm ci` → `npm run test -- --run` → `npm run build`

No Docker build or deployment occurs in this workflow.

#### `release.yml` — Main Branch Release

Triggers on push to `main` and supports manual `workflow_dispatch` with a `version_bump` input.

**`test` job** — same steps as `test.yml`.

**`build-and-deploy` job** (runs only on `main`, requires `test` to pass):

1. Checkout with `fetch-depth: 0`
2. Configure git identity (`Forgejo Actions` / `actions@forgejo`)
3. Write `deploy/.env` from the `TESSITURE_ENV` secret
4. Run `deploy/scripts/build.sh --version-bump {input|auto} --env-file deploy/.env --no-git-tag`
5. Run `deploy/scripts/deploy.sh --env-file deploy/.env --compose-file deploy/docker-compose.yml`
6. Inline health verification: poll container status for up to 120 s
7. Read `.release-version` → create annotated tag `v{version}` → push tag to Forgejo

### Runner Setup

Both workflows use `runs-on: self-hosted`. You must register a **self-hosted Forgejo Actions runner** (`act_runner`) on the Unraid host.

**Steps:**

1. Download `act_runner` from your Forgejo instance: **Settings → Actions → Runners** (or from the [Forgejo releases page](https://forgejo.org/releases/))
2. Generate a registration token from your repository: **Settings → Actions → Runners → New Runner**
3. Register the runner:
   ```bash
   ./act_runner register --instance https://your-forgejo.example.com --token <TOKEN> --name unraid-runner --labels self-hosted
   ```
4. Ensure Docker is available on the runner host — the runner executes `docker build` and `docker compose` directly against the host daemon
5. Start the runner as a persistent service (e.g., via Unraid's User Scripts plugin or a systemd unit)

> **Important:** The runner must run directly on the Unraid host (or with access to the host Docker socket). Do **not** run the runner inside a DinD container — the `build-and-deploy` job requires access to the host Docker daemon to deploy the Tessiture container.

### Required Secret: `TESSITURE_ENV`

The `release.yml` workflow writes `deploy/.env` from a Forgejo repository secret named `TESSITURE_ENV`. This secret must contain the **full contents** of your `deploy/.env` file (the same file you use for manual `make release` runs).

**To create the secret:**

1. Copy the full contents of your local `deploy/.env`
2. In Forgejo, navigate to your repository → **Settings** → **Secrets** → **Actions**
3. Click **New Secret**
4. **Name:** `TESSITURE_ENV`
5. **Value:** paste the full `deploy/.env` contents
6. Click **Save**

> **Keep this secret synchronized.** Whenever you update `TESSITURE_IMAGE`, `TESSITURE_CORS_ORIGINS`, host paths, or any other variable in your local `deploy/.env`, update the Forgejo secret to match. A stale secret will cause the CI deploy to use outdated configuration.

### `fetch-depth: 0` Requirement

Both workflows check out with `fetch-depth: 0` (full git history). This is required because [`deploy/scripts/build.sh`](../deploy/scripts/build.sh) uses `detect_auto_bump()`, which scans `git log` since the last `v*.*.*` tag to determine the appropriate version bump. A shallow clone (the default `fetch-depth: 1`) would produce an incomplete commit history, causing the auto-bump to always fall back to `patch` regardless of actual commit content.

### `--no-git-tag` in the Build Step

The `build-and-deploy` job calls `build.sh` with `--no-git-tag`. This prevents `build.sh` from creating a local git tag that would only exist on the runner's ephemeral workspace. Instead, the workflow reads `.release-version` after the build and explicitly creates and pushes the annotated tag to Forgejo in a dedicated step. This ensures the tag is visible in the Forgejo repository.

### Manual Release Trigger

`release.yml` supports `workflow_dispatch` with a `version_bump` input (`auto`, `patch`, `minor`, `major`, `none`). To trigger a manual release:

1. In Forgejo, navigate to your repository → **Actions** → **Release** workflow
2. Click **Run workflow**
3. Select the desired `version_bump` strategy (default: `auto`)
4. Click **Run workflow**

> A `major` version bump should only be used when the release contains breaking changes. See [AGENTS.md](../AGENTS.md) for the versioning policy.

### Tag Push and Verification

After a successful deploy, the workflow creates an annotated tag `v{version}` and pushes it to Forgejo. To verify in your local clone:

```bash
# Fetch tags from Forgejo
git fetch --tags

# List recent version tags
git tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-version:refname | head -5
```

You can also view tags in the Forgejo UI under **Repository → Tags**.

### Troubleshooting (Forgejo Actions)

| Symptom | Cause | Fix |
|---------|-------|-----|
| Job stays in "waiting" state | No self-hosted runner registered or runner is offline | Verify `act_runner` is running on the Unraid host; check runner status in Forgejo Settings → Actions → Runners |
| `TESSITURE_ENV secret not found` or empty `deploy/.env` | Secret not created or named incorrectly | Create the `TESSITURE_ENV` secret in Forgejo repository Settings → Secrets → Actions |
| Auto version bump always produces `patch` | Shallow clone — `fetch-depth` not set to `0` | Both workflow files already set `fetch-depth: 0`; verify the workflow files have not been modified |
| `docker: command not found` on runner | Docker not installed or not on PATH for the runner user | Install Docker on the Unraid host and ensure the runner user has access to the Docker socket |
| `caddy_proxy` network not found during deploy | Network does not exist on the Unraid host | Run `docker network create caddy_proxy` on the host, or deploy your Caddy stack first |
| Tag already exists error | A previous run created the tag; re-running the workflow | The workflow skips tag creation if the tag already exists — this is safe to ignore |
| Deploy succeeds but container is not healthy | Application startup error | Check container logs: `docker logs tessiture`; check `deploy/.env` for misconfigured paths or CORS origins |

---

## 5. First-Time Setup

```bash
# 1. Copy the environment template
cp deploy/.env.example deploy/.env

# 2. Edit deploy/.env — set at minimum:
#    - TESSITURE_IMAGE (your registry/repo:tag)
#    - TESSITURE_CORS_ORIGINS (your public hostname origin)
#    - TESSITURE_PUBLIC_HOSTNAME
#    - TESSITURE_UPLOAD_HOST_PATH, TESSITURE_OUTPUT_HOST_PATH,
#      TESSITURE_JOBS_HOST_PATH, TESSITURE_LOG_HOST_PATH

# 3. Install Python dependencies
make install-dev

# 4. Install frontend dependencies
cd frontend && npm ci && cd ..

# 5. Run the full release (build → deploy → verify)
make release
```

After `make release` completes, the container is running, healthy, and the version is tagged in git.

---

## 6. Environment File Reference

`deploy/.env` (copied from [`deploy/.env.example`](../deploy/.env.example)) is the single source of truth for all runtime configuration. The build and deploy scripts read from and write to this file.

### Image

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `TESSITURE_IMAGE` | `ghcr.io/your-org/tessiture:latest` | **Yes** | Docker image tag. Auto-updated by `build.sh` after each versioned build. |

### Runtime

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `TESSITURE_ENV` | `production` | No | Runtime environment label |
| `TESSITURE_HOST` | `0.0.0.0` | No | Bind address inside the container |
| `TESSITURE_PORT` | `8000` | No | Port the app listens on inside the container |
| `TESSITURE_LAN_BIND_PORT` | `8000` | No | Host loopback port (`127.0.0.1:PORT`) exposed to the host |

### Container Data Paths

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `TESSITURE_UPLOAD_DIR` | `/data/uploads` | No | Upload directory inside the container |
| `TESSITURE_OUTPUT_DIR` | `/data/outputs` | No | Output directory inside the container |
| `TESSITURE_EXAMPLES_DIR` | `/app/examples/tracks` | No | Example tracks directory inside the container |
| `TESSITURE_JOBS_DIR` | `/tmp/tessiture_jobs` | No | Job state directory inside the container |
| `TESSITURE_LOG_DIR` | `/tmp/tessiture_logs` | No | Log directory inside the container |

### Host Persistent Paths

These paths are bind-mounted from the Unraid host into the container. They are **auto-created** by `deploy.sh` if they do not exist.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `TESSITURE_UPLOAD_HOST_PATH` | `/mnt/user/appdata/tessiture/uploads` | **Yes** | Host path for uploaded audio files |
| `TESSITURE_OUTPUT_HOST_PATH` | `/mnt/user/appdata/tessiture/outputs` | **Yes** | Host path for analysis outputs |
| `TESSITURE_JOBS_HOST_PATH` | `/mnt/user/appdata/tessiture/jobs` | **Yes** | Host path for job state |
| `TESSITURE_LOG_HOST_PATH` | `/mnt/user/appdata/tessiture/logs` | **Yes** | Host path for logs |
| `TESSITURE_STEM_CACHE_HOST_PATH` | `/mnt/user/appdata/tessiture/stem_cache` | No | Host path for Demucs stem cache |

### Request Limits

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `TESSITURE_UPLOAD_MAX_BYTES` | `26214400` | No | Maximum upload size in bytes (default: 25 MB) |
| `TESSITURE_RATE_LIMIT_CAPACITY` | `10` | No | Token bucket capacity for rate limiting |
| `TESSITURE_RATE_LIMIT_REFILL_PER_SEC` | `0.5` | No | Token bucket refill rate per second |

### Public Hostname and CORS

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `TESSITURE_PUBLIC_HOSTNAME` | `tess.indecisivephysicist.space` | **Yes** | Public hostname; must match your Caddyfile site block and DNS |
| `TESSITURE_CORS_ORIGINS` | `https://voice.example.com` | **Yes** | Allowed CORS origins, comma-separated |

### Vocal Separation

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `TESSITURE_VOCAL_SEPARATION` | `auto` | No | `auto` enables Demucs if GPU is available; `disabled` skips separation |

### Release Metadata

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `TESSITURE_RELEASE_VERSION` | _(set by `one-shot.sh`)_ | No | Semantic version string injected at deploy time; synced from `.release-version` |

### Authentik (Optional, Disabled by Default)

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTHENTIK_FORWARD_AUTH_ENABLED` | `false` | Enable Authentik forward auth in Caddy |
| `AUTHENTIK_OUTPOST_ROUTE_ENABLED` | `false` | Enable Authentik outpost route in Caddy |
| `AUTHENTIK_DOMAIN` | `auth.example.com` | Authentik domain |
| `AUTHENTIK_OUTPOST_URL` | `http://authentik-proxy:9000` | Authentik outpost URL |
| `AUTHENTIK_FORWARD_AUTH_URI` | `/outpost.goauthentik.io/auth/caddy` | Forward auth URI |
| `AUTHENTIK_OUTPOST_PATH_PREFIX` | `/outpost.goauthentik.io` | Outpost path prefix |

---

## 7. Build System

### Overview

[`deploy/scripts/build.sh`](../deploy/scripts/build.sh) is the core build script. It:

1. Reads `TESSITURE_IMAGE` from `deploy/.env` (or accepts `--image` override)
2. Computes the next semantic version using the configured bump strategy
3. Builds the Docker image with `VITE_APP_VERSION` injected as a build arg (for frontend version display)
4. Optionally pushes the image to a registry (`--push`)
5. Writes the new version to `.release-version` in the repo root
6. Updates `TESSITURE_IMAGE` in `deploy/.env` to the new versioned tag
7. Creates an annotated git tag `v{version}` (e.g., `v1.3.0`)

### Versioning Strategy

The default strategy is `VERSION_BUMP=auto`. The script scans git commit subjects since the last `v*.*.*` tag and applies the highest-priority rule:

| Commit pattern | Effective bump |
|----------------|----------------|
| Subject contains `BREAKING CHANGE`, or matches `type!:` / `type(scope)!:` | **major** |
| Subject starts with `feat:` or `feat(scope):` | **minor** |
| All other commits | **patch** |

If no git history is available (e.g., shallow clone, no tags), the script falls back to a **patch** bump.

### Version Bump Options

| `VERSION_BUMP` value | Behavior |
|----------------------|----------|
| `auto` | Scan commits and apply highest-priority rule (default) |
| `patch` | Always bump patch component |
| `minor` | Always bump minor component, reset patch to 0 |
| `major` | Always bump major component, reset minor and patch to 0 |
| `none` | Do not bump; use existing image tag as-is |

### Git Tagging

After a successful build (when `VERSION_BUMP` is not `none`), the script creates an annotated git tag:

```bash
git tag -a v1.3.0 -m "Release v1.3.0"
```

To push tags to your remote:
```bash
git push --tags
```

To skip git tagging (useful for CI pipelines):
```bash
make build NO_GIT_TAG=1
# or directly:
deploy/scripts/build.sh --no-git-tag
```

### Release Version File

After a successful build, the resolved version is written to `.release-version` in the repo root:

```
1.3.0
```

This file is read by:
- `make build-frontend` — injects `VITE_APP_VERSION` for the frontend version display
- `deploy/scripts/one-shot.sh` — syncs `TESSITURE_RELEASE_VERSION` into `deploy/.env`

### Script Usage

```bash
# Default: auto-bump, read image from deploy/.env
deploy/scripts/build.sh

# Explicit image and version bump
deploy/scripts/build.sh --image ghcr.io/acme/tessiture:latest --version-bump auto

# Build, bump major, and push
deploy/scripts/build.sh --image ghcr.io/acme/tessiture:1.4.2 --version-bump major --push

# Skip git tagging
deploy/scripts/build.sh --no-git-tag

# All options
deploy/scripts/build.sh \
  --image ghcr.io/acme/tessiture:latest \
  --version-bump auto \
  --base-version 1.0.0 \
  --env-file deploy/.env \
  --push \
  --no-git-tag
```

### `--base-version`

When the current image tag is not a valid semver string (e.g., `latest`, `local`), the script uses `--base-version` (default: `0.0.0`) as the starting point for the bump calculation.

---

## 8. Deploy Script

[`deploy/scripts/deploy.sh`](../deploy/scripts/deploy.sh) runs `docker compose up -d` using the image and configuration in `deploy/.env`.

### What It Does

1. Validates that `deploy/.env` and `deploy/docker-compose.yml` exist
2. Reads `TESSITURE_IMAGE` from `deploy/.env` and verifies it is set
3. Reads the four host paths (`UPLOAD`, `OUTPUT`, `JOBS`, `LOG`) and **auto-creates** any that do not exist
4. Runs `docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d`
5. Prints the current service status via `docker compose ps`

### Script Usage

```bash
# Default: uses deploy/.env and deploy/docker-compose.yml
deploy/scripts/deploy.sh

# Override paths
deploy/scripts/deploy.sh --env-file deploy/.env --compose-file deploy/docker-compose.yml

# Run in attached mode (foreground, useful for debugging)
deploy/scripts/deploy.sh --no-detach
```

---

## 9. One-Shot Script (Primary Release)

[`deploy/scripts/one-shot.sh`](../deploy/scripts/one-shot.sh) orchestrates the full release pipeline:

```
Step 1/3: build image      (calls build.sh)
Step 2/3: deploy stack     (calls deploy.sh)
Step 3/3: verify health    (polls Docker healthcheck)
```

After the build step, `one-shot.sh` reads `.release-version` and syncs `TESSITURE_RELEASE_VERSION` into `deploy/.env` before deploying. This ensures the running container receives the correct version metadata.

### Health Verification

The script polls the container's Docker healthcheck status for up to `--verify-timeout` seconds (default: 120). If the container does not reach `healthy` within the timeout, the script exits with an error.

If no healthcheck is configured, the script passes as long as the container is in `running` state.

### Script Usage

```bash
# Default: auto-bump, uses deploy/.env
deploy/scripts/one-shot.sh

# Explicit version bump
deploy/scripts/one-shot.sh --version-bump minor

# Build, push, and deploy
deploy/scripts/one-shot.sh --image ghcr.io/acme/tessiture:latest --push

# Extend health verification timeout
deploy/scripts/one-shot.sh --verify-timeout 180
```

> **Prefer `make release` over calling `one-shot.sh` directly.** The Makefile target passes all standard arguments correctly.

---

## 10. Makefile Reference

The `Makefile` is the primary interface for all build and deploy operations. Run `make help` to see all targets.

### All Targets

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

**Deprecated aliases** (still functional, emit a deprecation notice):

| Deprecated | Use instead |
|------------|-------------|
| `make unraid-build` | `make build` |
| `make unraid-build-push` | `make build-push` |
| `make unraid-deploy` | `make deploy` |
| `make unraid-one-shot` | `make release` |

### Makefile Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VERSION_BUMP` | `auto` | Version bump strategy: `auto\|patch\|minor\|major\|none` |
| `BASE_VERSION` | `0.0.0` | Fallback version when image tag is not semver |
| `IMAGE` | _(from `deploy/.env`)_ | Override Docker image repo/tag |
| `ENV_FILE` | `deploy/.env` | Path to environment file |
| `COMPOSE_FILE` | `deploy/docker-compose.yml` | Path to compose file |
| `NO_GIT_TAG` | _(unset)_ | Set to `1` to skip git tagging |

### Examples

```bash
# Full release with auto version bump (most common)
make release

# Full release with explicit minor bump
make release VERSION_BUMP=minor

# Build only, no deploy
make build

# Build and push to a registry
make build-push IMAGE=ghcr.io/yourorg/tessiture

# Deploy only (uses image already set in deploy/.env)
make deploy

# Build without creating a git tag
make build NO_GIT_TAG=1

# Re-tag the current version in git without rebuilding
make tag
```

---

## 11. Networking

### Container Networks

The container joins two Docker networks:

| Network | Type | Purpose |
|---------|------|---------|
| `tessiture_internal` | Bridge (internal) | Isolated internal network; no external routing |
| `caddy_proxy` | External (pre-existing) | Shared network for Caddy reverse proxy routing |

The `caddy_proxy` network **must pre-exist** before deploying. It is created by your Caddy stack. If it does not exist, `docker compose up` will fail.

### Host Port Binding

The container also binds to the host loopback:

```
127.0.0.1:{TESSITURE_LAN_BIND_PORT} → container:{TESSITURE_PORT}
```

This allows host-network processes (e.g., a cloudflared daemon running directly on the Unraid host) to reach Tessiture without joining the Docker network.

### Caddy Configuration

The active Caddyfile is located **outside** this repository:

```
/mnt/user/appdata/caddy/Caddyfile
```

Any Caddy routing changes must be made directly to that file. Validate syntax before restarting Caddy. The Caddyfile is not tracked in this repository — call out any external-file changes in your deployment notes.

A typical Caddy site block for Tessiture routes by hostname to the container via the `caddy_proxy` network:

```caddy
tess.indecisivephysicist.space {
    reverse_proxy tessiture:{TESSITURE_PORT}
}
```

### Cloudflare Tunnel

Cloudflare Tunnel is external and shared — it is not deployed by this stack. Point your existing tunnel ingress at either:

- `http://127.0.0.1:{TESSITURE_LAN_BIND_PORT}` (if cloudflared runs on the host network), or
- `http://tessiture:{TESSITURE_PORT}` (if cloudflared is a container on the `caddy_proxy` network)

---

## 12. Updating / Re-deploying

### Day-to-Day Release

```bash
# Most common: full release with auto version bump
make release

# With explicit bump type
make release VERSION_BUMP=minor

# After release, push git tags to remote
git push --tags
```

### Deploy Only (No Rebuild)

If you have already built and pushed an image and just need to redeploy:

```bash
# Ensure TESSITURE_IMAGE in deploy/.env points to the desired image
make deploy
```

### Rollback

1. Edit `deploy/.env` and set `TESSITURE_IMAGE` back to the previous stable tag
2. Redeploy: `make deploy`
3. Verify: `docker ps` and run a smoke test

---

## 13. Deployment Checklist

### Pre-Flight

- [ ] `deploy/.env` exists and matches the shape of `deploy/.env.example`
- [ ] `TESSITURE_IMAGE` is set to the target image tag
- [ ] `TESSITURE_CORS_ORIGINS` includes your public hostname and any LAN hostname
- [ ] `TESSITURE_PUBLIC_HOSTNAME` matches your Caddyfile site block and DNS
- [ ] `caddy_proxy` Docker network exists on the host

### Build Quality Gate

- [ ] Run backend checks: `make test`, `make lint`, `make typecheck`
- [ ] If frontend changed: `cd frontend && npm run test && npm run build`

### Release

- [ ] Run `make release` (or `make release VERSION_BUMP=minor|major` as appropriate)
- [ ] Confirm `.release-version` was written with the expected version
- [ ] Confirm `TESSITURE_IMAGE` in `deploy/.env` was updated to the new versioned tag
- [ ] Confirm git tag was created: `git tag --list 'v*' | tail -5`
- [ ] Push tags to remote: `git push --tags`

### Smoke Test

- [ ] Open the app UI and submit a small audio file
- [ ] Verify full API flow: analyze → status polling → results download (JSON/CSV/PDF)
- [ ] Verify uploads and outputs are written to the configured host paths
- [ ] Check logs for CORS errors, 4xx spikes, or worker exceptions

### External Validation

- [ ] Confirm public hostname resolves and serves the updated version
- [ ] Confirm Caddy is routing correctly (check `/mnt/user/appdata/caddy/Caddyfile`)
- [ ] Confirm no unexpected internet exposure (Caddy remains the only ingress)

### Stabilization

- [ ] Monitor for 15–30 minutes: error rate, restart count, request latency, disk growth

---

## 14. Troubleshooting

### Container not starting or not healthy

```bash
# Check container status
docker ps -a --filter name=tessiture

# Check container logs
docker logs tessiture

# Check healthcheck history
docker inspect tessiture --format '{{json .State.Health}}' | python3 -m json.tool
```

**Common causes:**
- `TESSITURE_IMAGE` in `deploy/.env` points to an image that does not exist locally or in the registry
- A required host path does not exist and could not be created (permissions issue)
- The `caddy_proxy` network does not exist — create it or deploy your Caddy stack first

### `caddy_proxy` network not found

```bash
# Check if the network exists
docker network ls | grep caddy

# Create it manually if needed (Caddy stack should normally create it)
docker network create caddy-proxy
```

### Missing or empty `TESSITURE_IMAGE`

`deploy.sh` will exit with an error if `TESSITURE_IMAGE` is not set in `deploy/.env`. Ensure you have:
1. Copied `deploy/.env.example` to `deploy/.env`
2. Set `TESSITURE_IMAGE` to a valid image tag
3. Run `make build` at least once (which auto-updates `TESSITURE_IMAGE` to the versioned tag)

### Docker socket not accessible

If running `build.sh` or `one-shot.sh` from inside a container, the Docker socket must be mounted:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

The scripts detect whether they are running inside a container and emit a specific error message if the socket is missing.

### Version bump produces unexpected result

Check the git log since the last version tag:

```bash
# See the last semver tag
git tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-version:refname | head -5

# See commits since that tag
git log v1.2.3..HEAD --pretty=%s
```

The auto-bump algorithm scans commit subjects for `BREAKING CHANGE`, `type!:`, `feat:`, etc. If the bump is unexpected, check whether commit messages match the expected conventional commit format.

### CORS errors in browser

Ensure `TESSITURE_CORS_ORIGINS` in `deploy/.env` includes the exact origin (scheme + hostname + port) that the browser is using. Restart the container after changing this value:

```bash
make deploy
```

### Uploads or outputs not persisting

Verify the host paths are correctly set and mounted:

```bash
# Check what is mounted
docker inspect tessiture --format '{{json .Mounts}}' | python3 -m json.tool

# Verify the host paths exist and are writable
ls -la /mnt/user/appdata/tessiture/
```

### Checking the running version

```bash
# From the release version file
cat .release-version

# From the running container's environment
docker exec tessiture env | grep TESSITURE_RELEASE_VERSION

# From the API
curl http://127.0.0.1:8000/health
```
