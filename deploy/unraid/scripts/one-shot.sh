#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNRAID_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${UNRAID_DIR}/../.." && pwd)"
DEFAULT_ENV_FILE="${UNRAID_DIR}/.env.unraid"
DEFAULT_COMPOSE_FILE="${UNRAID_DIR}/docker-compose.yml"

IMAGE=""
PUSH=0
ENV_FILE="${DEFAULT_ENV_FILE}"
COMPOSE_FILE="${DEFAULT_COMPOSE_FILE}"
DETACH=1
VERIFY_TIMEOUT=120

usage() {
  cat <<'EOF'
Usage: deploy/unraid/scripts/one-shot.sh [OPTIONS]

Run one-shot Unraid maintenance:
  1) Build image
  2) Deploy compose stack
  3) Verify container health

Options:
  --image <tag>          Build this image tag (default: TESSITURE_IMAGE from env file, fallback tessiture:local)
  --push                 Push image after build (requires registry-qualified tag)
  --env-file <path>      Env file used by deploy and image inference (default: deploy/unraid/.env.unraid)
  --compose-file <path>  Compose file used by deploy (default: deploy/unraid/docker-compose.yml)
  --no-detach            Run deploy in attached mode
  --verify-timeout <s>   Seconds to wait for healthy status (default: 120)
  -h, --help             Show this help message

Examples:
  deploy/unraid/scripts/one-shot.sh
  deploy/unraid/scripts/one-shot.sh --image tessiture:local
  deploy/unraid/scripts/one-shot.sh --image ghcr.io/acme/tessiture:2026.02.1 --push
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
[[ -f "${ENV_FILE}" ]] || die "Env file not found: ${ENV_FILE}"
[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"

ENV_IMAGE="$(read_env_value TESSITURE_IMAGE "${ENV_FILE}" || true)"

if [[ -z "${IMAGE}" ]]; then
  if [[ -n "${ENV_IMAGE}" ]]; then
    IMAGE="${ENV_IMAGE}"
    log "Using build image from env file: ${IMAGE}"
  else
    IMAGE="tessiture:local"
    log "TESSITURE_IMAGE is not set in env file; defaulting build image to ${IMAGE}"
  fi
fi

if [[ -n "${ENV_IMAGE}" && "${IMAGE}" != "${ENV_IMAGE}" ]]; then
  die "Requested --image '${IMAGE}' does not match TESSITURE_IMAGE '${ENV_IMAGE}' in ${ENV_FILE}; update env file or use matching --image"
fi

BUILD_ARGS=(--image "${IMAGE}")
if [[ "${PUSH}" -eq 1 ]]; then
  BUILD_ARGS+=(--push)
fi

DEPLOY_ARGS=(--env-file "${ENV_FILE}" --compose-file "${COMPOSE_FILE}")
if [[ "${DETACH}" -eq 0 ]]; then
  DEPLOY_ARGS+=(--no-detach)
fi

log "Step 1/3: build image"
"${SCRIPT_DIR}/build.sh" "${BUILD_ARGS[@]}"

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
