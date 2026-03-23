#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_ENV_FILE="${REPO_ROOT}/deploy/.env"
DEFAULT_COMPOSE_FILE="${REPO_ROOT}/deploy/docker-compose.yml"
RELEASE_VERSION_FILE="${REPO_ROOT}/.release-version"
RELEASE_VERSION_ENV_KEY="TESSITURE_RELEASE_VERSION"

IMAGE=""
PUSH=0
ENV_FILE="${DEFAULT_ENV_FILE}"
COMPOSE_FILE="${DEFAULT_COMPOSE_FILE}"
DETACH=1
VERIFY_TIMEOUT=120
VERSION_BUMP="auto"
BASE_VERSION="0.0.0"

usage() {
  cat <<'EOF'
Usage: deploy/scripts/one-shot.sh [OPTIONS]

Run one-shot maintenance:
  1) Build image
  2) Deploy compose stack
  3) Verify container health

Options:
  --image <tag>            Build this image tag/repo seed (defaults to TESSITURE_IMAGE from env)
  --push                   Push image after build (requires registry-qualified tag)
  --version-bump <kind>    Version strategy: auto|patch|minor|major|none (default: auto)
  --base-version <x.y.z>   Base version if current tag is non-semantic (default: 0.0.0)
  --env-file <path>        Env file used by build/deploy (default: deploy/.env)
  --compose-file <path>    Compose file used by deploy (default: deploy/docker-compose.yml)
  --no-detach              Run deploy in attached mode
  --verify-timeout <s>     Seconds to wait for healthy status (default: 120)
  -h, --help               Show this help message

Examples:
  deploy/scripts/one-shot.sh
  deploy/scripts/one-shot.sh --version-bump auto
  deploy/scripts/one-shot.sh --image ghcr.io/acme/tessiture:1.4.2 --version-bump major --push
EOF
}

log() {
  printf '[one-shot] %s\n' "$*"
}

die() {
  printf '[one-shot] ERROR: %s\n' "$*" >&2
  exit 1
}

resolve_path() {
  local candidate="$1"
  if [[ "${candidate}" = /* ]]; then
    printf '%s\n' "${candidate}"
  else
    printf '%s\n' "${REPO_ROOT}/${candidate}"
  fi
}

read_env_value() {
  local key="$1"
  local file="$2"
  local line

  line="$(grep -E "^[[:space:]]*${key}=" "${file}" | tail -n1 || true)"
  [[ -n "${line}" ]] || return 1
  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  line="${line%\'}"
  line="${line#\'}"
  printf '%s\n' "${line}"
}

parse_semver() {
  local raw="${1#v}"
  if [[ "${raw}" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    SEMVER_MAJOR="${BASH_REMATCH[1]}"
    SEMVER_MINOR="${BASH_REMATCH[2]}"
    SEMVER_PATCH="${BASH_REMATCH[3]}"
    return 0
  fi
  return 1
}

upsert_env_value() {
  local key="$1"
  local value="$2"
  local file="$3"
  local tmp_file

  tmp_file="$(mktemp)"
  awk -v key="${key}" -v value="${value}" '
    BEGIN { updated = 0 }
    $0 ~ "^[[:space:]]*" key "=" {
      print key "=" value
      updated = 1
      next
    }
    { print }
    END {
      if (updated == 0) {
        print key "=" value
      }
    }
  ' "${file}" > "${tmp_file}"
  mv "${tmp_file}" "${file}"
}

remove_env_key() {
  local key="$1"
  local file="$2"
  local tmp_file

  tmp_file="$(mktemp)"
  awk -v key="${key}" '$0 !~ "^[[:space:]]*" key "=" { print }' "${file}" > "${tmp_file}"
  mv "${tmp_file}" "${file}"
}

sync_release_metadata() {
  local env_file="$1"
  local raw_version
  local normalized_version

  if [[ ! -f "${RELEASE_VERSION_FILE}" ]]; then
    remove_env_key "${RELEASE_VERSION_ENV_KEY}" "${env_file}"
    log "${RELEASE_VERSION_FILE} not found after build; cleared ${RELEASE_VERSION_ENV_KEY} in ${env_file}"
    return
  fi

  raw_version="$(tr -d '[:space:]' < "${RELEASE_VERSION_FILE}")"
  if parse_semver "${raw_version}"; then
    normalized_version="${SEMVER_MAJOR}.${SEMVER_MINOR}.${SEMVER_PATCH}"
    upsert_env_value "${RELEASE_VERSION_ENV_KEY}" "${normalized_version}" "${env_file}"
    log "Using ${RELEASE_VERSION_FILE} as canonical release metadata source: ${RELEASE_VERSION_ENV_KEY}=${normalized_version}"
  else
    remove_env_key "${RELEASE_VERSION_ENV_KEY}" "${env_file}"
    log "Ignoring non-semantic ${RELEASE_VERSION_FILE} value '${raw_version}'; cleared ${RELEASE_VERSION_ENV_KEY} in ${env_file}"
  fi
}

is_container_runtime() {
  [[ -f "/.dockerenv" ]] && return 0
  grep -qaE '(docker|containerd|kubepods|lxc)' /proc/1/cgroup 2>/dev/null
}

docker_preflight() {
  local runtime_context="host"
  if is_container_runtime; then
    runtime_context="container"
  fi

  log "Docker preflight: context=${runtime_context}"

  if ! command -v docker >/dev/null 2>&1; then
    if [[ "${runtime_context}" = "container" ]]; then
      die "Docker CLI is missing in this container. Run this script from the Unraid host, or install docker CLI and mount /var/run/docker.sock."
    fi
    die "Docker CLI is missing on host. Install Docker Engine/CLI and retry."
  fi

  # Allow TCP-based Docker connections (e.g. DinD via DOCKER_HOST) in addition to socket
  if [[ "${runtime_context}" = "container" && ! -S "/var/run/docker.sock" && -z "${DOCKER_HOST:-}" ]]; then
    die "Docker socket /var/run/docker.sock is not available in this container. Run on host, mount the Docker socket, or set DOCKER_HOST to a TCP endpoint."
  fi

  if ! docker info >/dev/null 2>&1; then
    if [[ "${runtime_context}" = "container" ]]; then
      die "Docker daemon is unreachable from this container. Ensure /var/run/docker.sock is mounted with correct permissions, or run on host."
    fi
    die "Docker daemon is not reachable. Start Docker and retry."
  fi

  if ! docker compose version >/dev/null 2>&1; then
    die "Docker Compose v2 plugin is required (docker compose)."
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      [[ $# -ge 2 ]] || die "Missing value for --image"
      IMAGE="$2"
      shift 2
      ;;
    --push)
      PUSH=1
      shift
      ;;
    --version-bump)
      [[ $# -ge 2 ]] || die "Missing value for --version-bump"
      VERSION_BUMP="$2"
      shift 2
      ;;
    --base-version)
      [[ $# -ge 2 ]] || die "Missing value for --base-version"
      BASE_VERSION="$2"
      shift 2
      ;;
    --env-file)
      [[ $# -ge 2 ]] || die "Missing value for --env-file"
      ENV_FILE="$(resolve_path "$2")"
      shift 2
      ;;
    --compose-file)
      [[ $# -ge 2 ]] || die "Missing value for --compose-file"
      COMPOSE_FILE="$(resolve_path "$2")"
      shift 2
      ;;
    --no-detach)
      DETACH=0
      shift
      ;;
    --verify-timeout)
      [[ $# -ge 2 ]] || die "Missing value for --verify-timeout"
      VERIFY_TIMEOUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

[[ "${VERIFY_TIMEOUT}" =~ ^[0-9]+$ ]] || die "--verify-timeout must be a non-negative integer"
case "${VERSION_BUMP}" in
  auto|patch|minor|major|none) ;;
  *) die "--version-bump must be one of: auto, patch, minor, major, none" ;;
esac
[[ "${BASE_VERSION}" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "--base-version must be semantic (x.y.z)"
[[ -f "${ENV_FILE}" ]] || die "Env file not found: ${ENV_FILE}"
[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"

ENV_IMAGE="$(read_env_value TESSITURE_IMAGE "${ENV_FILE}" || true)"

if [[ -z "${IMAGE}" ]]; then
  if [[ -n "${ENV_IMAGE}" ]]; then
    IMAGE="${ENV_IMAGE}"
    log "Using build image seed from env file: ${IMAGE}"
  else
    IMAGE="tessiture:local"
    log "TESSITURE_IMAGE is not set in env file; defaulting build image seed to ${IMAGE}"
  fi
fi

if [[ -n "${ENV_IMAGE}" && "${IMAGE}" != "${ENV_IMAGE}" ]]; then
  log "Image seed override requested: --image ${IMAGE} (env currently ${ENV_IMAGE})"
fi

docker_preflight

BUILD_ARGS=(
  --image "${IMAGE}"
  --env-file "${ENV_FILE}"
  --version-bump "${VERSION_BUMP}"
  --base-version "${BASE_VERSION}"
)
if [[ "${PUSH}" -eq 1 ]]; then
  BUILD_ARGS+=(--push)
fi

DEPLOY_ARGS=(--env-file "${ENV_FILE}" --compose-file "${COMPOSE_FILE}")
if [[ "${DETACH}" -eq 0 ]]; then
  DEPLOY_ARGS+=(--no-detach)
fi

log "Step 1/3: build image"
"${SCRIPT_DIR}/build.sh" "${BUILD_ARGS[@]}"

sync_release_metadata "${ENV_FILE}"

DEPLOY_IMAGE="$(read_env_value TESSITURE_IMAGE "${ENV_FILE}" || true)"
if [[ -n "${DEPLOY_IMAGE}" ]]; then
  log "Image selected for deploy: ${DEPLOY_IMAGE}"
fi

DEPLOY_RELEASE_VERSION="$(read_env_value "${RELEASE_VERSION_ENV_KEY}" "${ENV_FILE}" || true)"
if [[ -n "${DEPLOY_RELEASE_VERSION}" ]]; then
  log "Release metadata selected for deploy: ${DEPLOY_RELEASE_VERSION}"
fi

log "Step 2/3: deploy stack"
"${SCRIPT_DIR}/deploy.sh" "${DEPLOY_ARGS[@]}"

log "Step 3/3: verify deployment"
CONTAINER_ID="$(docker ps -q --filter "name=^/tessiture$" | head -n1 || true)"
[[ -n "${CONTAINER_ID}" ]] || die "Container 'tessiture' is not running after deploy"

STATUS="$(docker inspect --format '{{.State.Status}}' "${CONTAINER_ID}")"
[[ "${STATUS}" = "running" ]] || die "Container is not running (status=${STATUS})"

HEALTH_STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${CONTAINER_ID}")"
if [[ "${HEALTH_STATUS}" = "none" ]]; then
  log "Healthcheck not configured; running-state verification passed"
else
  START_TIME="$(date +%s)"
  while [[ "${HEALTH_STATUS}" = "starting" ]]; do
    NOW="$(date +%s)"
    if (( NOW - START_TIME > VERIFY_TIMEOUT )); then
      die "Timed out waiting for healthy status after ${VERIFY_TIMEOUT}s"
    fi
    sleep 2
    HEALTH_STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${CONTAINER_ID}")"
  done

  [[ "${HEALTH_STATUS}" = "healthy" ]] || die "Healthcheck status is '${HEALTH_STATUS}'"
  log "Container healthcheck reports healthy"
fi

log "One-shot maintenance completed successfully"
