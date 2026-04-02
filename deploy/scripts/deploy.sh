#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_ENV_FILE="${REPO_ROOT}/deploy/.env"
DEFAULT_COMPOSE_FILE="${REPO_ROOT}/deploy/docker-compose.yml"
ENV_FILE="${DEFAULT_ENV_FILE}"
COMPOSE_FILE="${DEFAULT_COMPOSE_FILE}"
DETACH=1

usage() {
  cat <<'EOF'
Usage: deploy/scripts/deploy.sh [OPTIONS]

Deploy Tessiture using docker compose and deploy/.env.

Options:
  --env-file <path>      Override env file path (default: deploy/.env)
  --compose-file <path>  Override compose file path (default: deploy/docker-compose.yml)
  --no-detach            Run compose in attached mode
  -h, --help             Show this help message

Examples:
  deploy/scripts/deploy.sh
  deploy/scripts/deploy.sh --env-file deploy/.env
EOF
}

log() {
  printf '[deploy] %s\n' "$*"
}

die() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
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
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

require_cmd docker

docker info >/dev/null 2>&1 || die "Docker daemon is not reachable"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 plugin is required"

[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
[[ -f "${ENV_FILE}" ]] || die "Env file not found: ${ENV_FILE}"

TESSITURE_IMAGE="$(read_env_value TESSITURE_IMAGE "${ENV_FILE}" || true)"
[[ -n "${TESSITURE_IMAGE}" ]] || die "TESSITURE_IMAGE is missing or empty in ${ENV_FILE}"

UPLOAD_HOST_PATH="$(read_env_value TESSITURE_UPLOAD_HOST_PATH "${ENV_FILE}" || true)"
OUTPUT_HOST_PATH="$(read_env_value TESSITURE_OUTPUT_HOST_PATH "${ENV_FILE}" || true)"
JOBS_HOST_PATH="$(read_env_value TESSITURE_JOBS_HOST_PATH "${ENV_FILE}" || true)"
LOG_HOST_PATH="$(read_env_value TESSITURE_LOG_HOST_PATH "${ENV_FILE}" || true)"

[[ -n "${UPLOAD_HOST_PATH}" ]] || die "TESSITURE_UPLOAD_HOST_PATH is missing or empty in ${ENV_FILE}"
[[ -n "${OUTPUT_HOST_PATH}" ]] || die "TESSITURE_OUTPUT_HOST_PATH is missing or empty in ${ENV_FILE}"
[[ -n "${JOBS_HOST_PATH}" ]] || die "TESSITURE_JOBS_HOST_PATH is missing or empty in ${ENV_FILE}"
[[ -n "${LOG_HOST_PATH}" ]] || die "TESSITURE_LOG_HOST_PATH is missing or empty in ${ENV_FILE}"

if [[ ! -d "${UPLOAD_HOST_PATH}" ]]; then
  log "Creating missing upload host path: ${UPLOAD_HOST_PATH}"
  mkdir -p "${UPLOAD_HOST_PATH}" || die "Unable to create upload host path: ${UPLOAD_HOST_PATH}"
fi

if [[ ! -d "${OUTPUT_HOST_PATH}" ]]; then
  log "Creating missing output host path: ${OUTPUT_HOST_PATH}"
  mkdir -p "${OUTPUT_HOST_PATH}" || die "Unable to create output host path: ${OUTPUT_HOST_PATH}"
fi

if [[ ! -d "${JOBS_HOST_PATH}" ]]; then
  log "Creating missing jobs host path: ${JOBS_HOST_PATH}"
  mkdir -p "${JOBS_HOST_PATH}" || die "Unable to create jobs host path: ${JOBS_HOST_PATH}"
fi

if [[ ! -d "${LOG_HOST_PATH}" ]]; then
  log "Creating missing log host path: ${LOG_HOST_PATH}"
  mkdir -p "${LOG_HOST_PATH}" || die "Unable to create log host path: ${LOG_HOST_PATH}"
fi

log "Repo root: ${REPO_ROOT}"
log "Compose file: ${COMPOSE_FILE}"
log "Env file: ${ENV_FILE}"
log "Deploying image: ${TESSITURE_IMAGE}"

COMPOSE_CMD=(docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}")

if [[ "${DETACH}" -eq 1 ]]; then
  "${COMPOSE_CMD[@]}" up -d
else
  "${COMPOSE_CMD[@]}" up
fi

log "Current service status:"
"${COMPOSE_CMD[@]}" ps

CONTAINER_STATUS="$(docker ps --filter "name=^/tessiture$" --format '{{.Status}}' | head -n1 || true)"
if [[ -n "${CONTAINER_STATUS}" ]]; then
  log "Container status: ${CONTAINER_STATUS}"
else
  log "Container status unavailable from docker ps; check compose output above"
fi

log "Deploy completed"
