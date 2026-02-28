#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

DEFAULT_IMAGE="tessiture:local"
IMAGE="${DEFAULT_IMAGE}"
PUSH=0

usage() {
  cat <<'EOF'
Usage: deploy/unraid/scripts/build.sh [OPTIONS]

Build the Tessiture Docker image from the repository root.

Options:
  --image <tag>   Docker image tag to build (default: tessiture:local)
  --push          Push image to registry after successful build
  -h, --help      Show this help message

Examples:
  deploy/unraid/scripts/build.sh
  deploy/unraid/scripts/build.sh --image ghcr.io/acme/tessiture:2026.02.1
  deploy/unraid/scripts/build.sh --image ghcr.io/acme/tessiture:2026.02.1 --push
EOF
}

log() {
  printf '[build] %s\n' "$*"
}

die() {
  printf '[build] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
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
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

[[ -n "${IMAGE}" ]] || die "Image tag cannot be empty"

require_cmd docker

docker info >/dev/null 2>&1 || die "Docker daemon is not reachable"

if [[ "${PUSH}" -eq 1 && "${IMAGE}" != */* ]]; then
  die "--push requires a registry-qualified image tag (example: ghcr.io/<org>/tessiture:<tag>)"
fi

log "Repository root: ${REPO_ROOT}"
log "Building image: ${IMAGE}"
docker build -t "${IMAGE}" "${REPO_ROOT}"

if [[ "${PUSH}" -eq 1 ]]; then
  log "Pushing image: ${IMAGE}"
  docker push "${IMAGE}"
fi

IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${IMAGE}" 2>/dev/null || true)"
if [[ -n "${IMAGE_ID}" ]]; then
  log "Build complete: ${IMAGE} (${IMAGE_ID})"
else
  log "Build complete: ${IMAGE}"
fi
