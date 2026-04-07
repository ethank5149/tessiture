#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_IMAGE="tessiture:local"
IMAGE="${DEFAULT_IMAGE}"
IMAGE_SET=0
PUSH=0
VERSION_BUMP="auto"
BASE_VERSION="0.0.0"
ENV_FILE=""
RELEASE_VERSION_FILE="${REPO_ROOT}/.release-version"
RELEASE_VERSION=""
NO_GIT_TAG=0
CACHE_REF=""
NO_CACHE=0

usage() {
  cat <<'EOF'
Usage: deploy/scripts/build.sh [OPTIONS]

Build the Tessiture Docker image from the repository root.

Options:
  --image <tag>            Docker image tag/repo to build (default: tessiture:local)
  --push                   Push image to registry after successful build
  --version-bump <kind>    Version strategy: auto|patch|minor|major|none (default: auto)
  --base-version <x.y.z>  Base version when current image tag is not semantic (default: 0.0.0)
  --env-file <path>        Optional env file to read/update TESSITURE_IMAGE
  --cache-ref <tag>        Registry reference for BuildKit cache (e.g., registry/repo:buildcache)
  --no-git-tag             Skip creating a git tag after successful build
  -h, --help               Show this help message

Examples:
  deploy/scripts/build.sh
  deploy/scripts/build.sh --image ghcr.io/acme/tessiture:latest --version-bump auto
  deploy/scripts/build.sh --image ghcr.io/acme/tessiture:1.4.2 --version-bump major --push
  deploy/scripts/build.sh --no-git-tag
EOF
}

log()         { printf '[build] %s\n' "$*"; }
die()         { printf '[build] ERROR: %s\n' "$*" >&2; exit 1; }
require_cmd() { command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"; }

is_container_runtime() {
  [[ -f "/.dockerenv" ]] && return 0
  grep -qaE '(docker|containerd|kubepods|lxc)' /proc/1/cgroup 2>/dev/null
}

docker_preflight() {
  local runtime_context="host"
  is_container_runtime && runtime_context="container"
  log "Docker preflight: context=${runtime_context}"

  command -v docker >/dev/null 2>&1 || die "Docker CLI is missing."

  if [[ "${runtime_context}" = "container" && ! -S "/var/run/docker.sock" && -z "${DOCKER_HOST:-}" ]]; then
    die "Docker socket unavailable and DOCKER_HOST unset."
  fi

  if ! docker info >/dev/null 2>&1; then
    if [[ "${DOCKER_HOST:-}" == *":2376"* ]]; then
      local alt_host="${DOCKER_HOST//:2376/:2375}"
      log "TLS connection failed; trying non-TLS fallback: ${alt_host}"
      unset DOCKER_TLS_VERIFY DOCKER_CERT_PATH 2>/dev/null || true
      export DOCKER_HOST="${alt_host}"
      if docker info >/dev/null 2>&1; then
        log "Connected via non-TLS fallback (${alt_host})"
        return 0
      fi
    fi
    die "Docker daemon is not reachable."
  fi
}

setup_buildx() {
  if ! docker buildx version >/dev/null 2>&1; then
    log "WARNING: docker buildx not available; falling back to docker build"
    return 1
  fi

  # Always recreate the builder so driver options are applied fresh.
  docker buildx rm tessiture-builder 2>/dev/null || true

  # Use docker driver (not docker-container) when we want to load the image locally.
  # docker-container driver requires --push and doesn't support --load well.
  # Only use docker-container when pushing to a registry.
  if [[ "${PUSH}" -eq 1 ]]; then
    local -a create_args=(
      --name tessiture-builder
      --driver docker-container
      --driver-opt network=host
      --use
    )
  else
    # Use docker driver for local builds (supports --load)
    docker buildx create --name tessiture-builder --driver docker --use
    return 0
  fi

  # With TCP-based DinD, the buildkit container runs inside DinD and has no
  # filesystem access to the job container's ~/.docker/config.json.
  # BuildKit natively supports DOCKER_AUTH_CONFIG as an env var for registry
  # auth, so we read the local config and inject it into the buildkit container.
  local docker_config_file="${DOCKER_CONFIG:-${HOME}/.docker}/config.json"
  if [[ -f "${docker_config_file}" ]]; then
    local auth_config
    auth_config="$(cat "${docker_config_file}")"
    create_args+=(--driver-opt "env.DOCKER_AUTH_CONFIG=${auth_config}")
    log "Injecting registry credentials into buildkit container"
  else
    log "WARNING: No docker config found at ${docker_config_file}; registry push may fail"
  fi

  docker buildx create "${create_args[@]}"
  docker buildx inspect --bootstrap >/dev/null 2>&1 || true
  return 0
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
  local key="$1" file="$2" line
  line="$(grep -E "^[[:space:]]*${key}=" "${file}" | tail -n1 || true)"
  [[ -n "${line}" ]] || return 1
  line="${line#*=}"; line="${line%\"}"; line="${line#\"}"; line="${line%\'}"; line="${line#\'}"
  printf '%s\n' "${line}"
}

split_image_ref() {
  local ref="$1"
  if [[ "${ref##*/}" == *:* ]]; then
    IMAGE_REPO="${ref%:*}"; IMAGE_TAG="${ref##*:}"
  else
    IMAGE_REPO="${ref}"; IMAGE_TAG="latest"
  fi
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

bump_semver() {
  local current="$1" bump_kind="$2"
  parse_semver "${current}" || return 1
  local major="${SEMVER_MAJOR}" minor="${SEMVER_MINOR}" patch="${SEMVER_PATCH}"
  case "${bump_kind}" in
    major) major=$((major + 1)); minor=0; patch=0 ;;
    minor) minor=$((minor + 1)); patch=0 ;;
    patch) patch=$((patch + 1)) ;;
    *)     return 1 ;;
  esac
  printf '%s.%s.%s\n' "${major}" "${minor}" "${patch}"
}

detect_auto_bump() {
  if ! command -v git >/dev/null 2>&1 || \
     ! git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'patch\n'; return
  fi
  local last_semver_tag range subjects
  last_semver_tag="$(git -C "${REPO_ROOT}" tag --list 'v[0-9]*.[0-9]*.[0-9]*' \
    --sort=-version:refname | head -n1 || true)"
  range="HEAD"
  [[ -n "${last_semver_tag}" ]] && range="${last_semver_tag}..HEAD"
  subjects="$(git -C "${REPO_ROOT}" log --pretty=%s ${range} 2>/dev/null || true)"

  if [[ -n "${subjects}" ]] && grep -qiE '(BREAKING CHANGE)|(^[a-z]+(\([^)]+\))?!:)' <<<"${subjects}"; then
    printf 'major\n'
  elif [[ -n "${subjects}" ]] && grep -qiE '(^feat(\(.+\))?:)|(^feature(\(.+\))?:)' <<<"${subjects}"; then
    printf 'minor\n'
  else
    printf 'patch\n'
  fi
}

update_env_image() {
  local env_file="$1" image="$2" tmp_file
  tmp_file="$(mktemp)"
  awk -v image="${image}" '
    BEGIN { updated = 0 }
    /^[[:space:]]*TESSITURE_IMAGE=/ { print "TESSITURE_IMAGE=" image; updated = 1; next }
    { print }
    END { if (!updated) print "TESSITURE_IMAGE=" image }
  ' "${env_file}" > "${tmp_file}"
  mv "${tmp_file}" "${env_file}"
}

write_release_version_file() {
  printf '%s\n' "$1" > "${RELEASE_VERSION_FILE}"
  log "Wrote release version: $1"
}

clear_release_version_file() {
  if [[ -f "${RELEASE_VERSION_FILE}" ]]; then
    rm -f "${RELEASE_VERSION_FILE}"
    log "No semantic version resolved; removed stale ${RELEASE_VERSION_FILE}"
  fi
}

git_tag_release() {
  local tag="v${1}"
  [[ "${NO_GIT_TAG}" -eq 1 ]] && { log "Skipping git tag (--no-git-tag)"; return; }
  command -v git >/dev/null 2>&1 || { log "WARNING: git not available; skipping tag"; return; }
  git -C "${REPO_ROOT}" rev-parse --git-dir >/dev/null 2>&1 || { log "WARNING: not a git repo; skipping tag"; return; }
  git -C "${REPO_ROOT}" tag --list "${tag}" | grep -q "^${tag}$" && { log "Tag ${tag} already exists; skipping"; return; }
  git -C "${REPO_ROOT}" tag -a "${tag}" -m "Release ${tag}"
  log "Tagged release: ${tag}"
}

# ── Argument parsing ──────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)        [[ $# -ge 2 ]] || die "Missing value for --image";        IMAGE="$2";                    IMAGE_SET=1; shift 2 ;;
    --push)         PUSH=1; shift ;;
    --version-bump) [[ $# -ge 2 ]] || die "Missing value for --version-bump"; VERSION_BUMP="$2";              shift 2 ;;
    --base-version) [[ $# -ge 2 ]] || die "Missing value for --base-version"; BASE_VERSION="$2";              shift 2 ;;
    --env-file)     [[ $# -ge 2 ]] || die "Missing value for --env-file";     ENV_FILE="$(resolve_path "$2")"; shift 2 ;;
    --cache-ref)    [[ $# -ge 2 ]] || die "Missing value for --cache-ref";    CACHE_REF="$2";                shift 2 ;;
    --no-git-tag)   NO_GIT_TAG=1; shift ;;
    --no-cache)     NO_CACHE=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *)              die "Unknown argument: $1" ;;
  esac
done

case "${VERSION_BUMP}" in
  auto|patch|minor|major|none) ;;
  *) die "--version-bump must be one of: auto, patch, minor, major, none" ;;
esac

parse_semver "${BASE_VERSION}" || die "--base-version must be semantic version (x.y.z)"
BASE_VERSION="${SEMVER_MAJOR}.${SEMVER_MINOR}.${SEMVER_PATCH}"

if [[ -n "${ENV_FILE}" ]]; then
  [[ -f "${ENV_FILE}" ]] || die "Env file not found: ${ENV_FILE}"
  if [[ "${IMAGE_SET}" -eq 0 ]]; then
    ENV_IMAGE="$(read_env_value TESSITURE_IMAGE "${ENV_FILE}" || true)"
    if [[ -n "${ENV_IMAGE}" ]]; then
      IMAGE="${ENV_IMAGE}"
      log "Using image from env file: ${IMAGE}"
    fi
  fi
fi

[[ -n "${IMAGE}" ]] || die "Image tag cannot be empty"

require_cmd docker
docker_preflight
split_image_ref "${IMAGE}"

# ── Version resolution ────────────────────────────────────────────────────────

LATEST_IMAGE=""
if [[ "${VERSION_BUMP}" != "none" ]]; then
  local_version=""
  if parse_semver "${IMAGE_TAG}"; then
    local_version="${SEMVER_MAJOR}.${SEMVER_MINOR}.${SEMVER_PATCH}"
  else
    local_version="${BASE_VERSION}"
    log "Image tag '${IMAGE_TAG}' is not semantic; using base version ${local_version}"
  fi

  EFFECTIVE_BUMP="${VERSION_BUMP}"
  [[ "${VERSION_BUMP}" = "auto" ]] && EFFECTIVE_BUMP="$(detect_auto_bump)"

  NEXT_VERSION="$(bump_semver "${local_version}" "${EFFECTIVE_BUMP}")" || die "Unable to bump version"
  IMAGE="${IMAGE_REPO}:${NEXT_VERSION}"
  LATEST_IMAGE="${IMAGE_REPO}:latest"
  RELEASE_VERSION="${NEXT_VERSION}"

  log "Version bump: ${VERSION_BUMP} (effective=${EFFECTIVE_BUMP})"
  log "Version: ${local_version} -> ${NEXT_VERSION}"
else
  if parse_semver "${IMAGE_TAG}"; then
    RELEASE_VERSION="${SEMVER_MAJOR}.${SEMVER_MINOR}.${SEMVER_PATCH}"
    log "Version bump: none; using tag: ${RELEASE_VERSION}"
  else
    log "Version bump: none; tag '${IMAGE_TAG}' not semantic — release version file will not be written"
  fi
fi

[[ "${PUSH}" -eq 1 && "${IMAGE}" != */* ]] && \
  die "--push requires a registry-qualified image tag (e.g. ghcr.io/<org>/tessiture:<tag>)"

log "Repository root: ${REPO_ROOT}"
log "Building image:  ${IMAGE}"

# ── Build ─────────────────────────────────────────────────────────────────────

USE_BUILDX=0
setup_buildx && USE_BUILDX=1

if [[ "${USE_BUILDX}" -eq 1 ]]; then
  BUILD_CMD=(docker buildx build --provenance=false -t "${IMAGE}" --load)
  [[ "${NO_CACHE}" -eq 1 ]] && BUILD_CMD+=(--no-cache)
  [[ -n "${LATEST_IMAGE}" && "${LATEST_IMAGE}" != "${IMAGE}" ]] && BUILD_CMD+=(-t "${LATEST_IMAGE}")
  if [[ -n "${CACHE_REF}" ]]; then
    BUILD_CMD+=(--cache-from "type=registry,ref=${CACHE_REF}")
    BUILD_CMD+=(--cache-to   "type=registry,ref=${CACHE_REF},mode=max")
    log "BuildKit registry cache: ${CACHE_REF}"
  fi
  [[ "${PUSH}" -eq 1 ]]         && BUILD_CMD+=(--push)
  [[ -n "${RELEASE_VERSION}" ]] && BUILD_CMD+=(--build-arg "VITE_APP_VERSION=${RELEASE_VERSION}")
  BUILD_CMD+=("${REPO_ROOT}")
  log "Building with docker buildx"
  "${BUILD_CMD[@]}"
else
  BUILD_CMD=(docker build -t "${IMAGE}")
  [[ "${NO_CACHE}" -eq 1 ]] && BUILD_CMD+=(--no-cache)
  [[ -n "${RELEASE_VERSION}" ]] && BUILD_CMD+=(--build-arg "VITE_APP_VERSION=${RELEASE_VERSION}")
  [[ -n "${LATEST_IMAGE}" && "${LATEST_IMAGE}" != "${IMAGE}" ]] && BUILD_CMD+=(-t "${LATEST_IMAGE}")
  BUILD_CMD+=("${REPO_ROOT}")
  log "Building with docker build (fallback, no registry cache)"
  "${BUILD_CMD[@]}"
fi

# ── Post-build ────────────────────────────────────────────────────────────────

[[ -n "${ENV_FILE}" && "${VERSION_BUMP}" != "none" ]] && {
  update_env_image "${ENV_FILE}" "${IMAGE}"
  log "Updated ${ENV_FILE}: TESSITURE_IMAGE=${IMAGE}"
}

if [[ -n "${RELEASE_VERSION}" ]]; then
  write_release_version_file "${RELEASE_VERSION}"
else
  clear_release_version_file
fi

[[ "${VERSION_BUMP}" != "none" && -n "${RELEASE_VERSION}" ]] && git_tag_release "${RELEASE_VERSION}"

IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${IMAGE}" 2>/dev/null || true)"
if [[ -n "${IMAGE_ID}" ]]; then
  log "Build complete: ${IMAGE} (${IMAGE_ID})"
else
  log "Build complete: ${IMAGE}"
fi