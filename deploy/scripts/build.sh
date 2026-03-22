#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

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

usage() {
  cat <<'EOF'
Usage: deploy/scripts/build.sh [OPTIONS]

Build the Tessiture Docker image from the repository root.

Options:
  --image <tag>            Docker image tag/repo to build (default: tessiture:local)
  --push                   Push image to registry after successful build
  --version-bump <kind>    Version strategy: auto|patch|minor|major|none (default: auto)
  --base-version <x.y.z>   Base version when current image tag is not semantic (default: 0.0.0)
  --env-file <path>        Optional env file to read/update TESSITURE_IMAGE
  --no-git-tag             Skip creating a git tag after successful build
  -h, --help               Show this help message

Examples:
  deploy/scripts/build.sh
  deploy/scripts/build.sh --image ghcr.io/acme/tessiture:latest --version-bump auto
  deploy/scripts/build.sh --image ghcr.io/acme/tessiture:1.4.2 --version-bump major --push
  deploy/scripts/build.sh --no-git-tag
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
      die "Docker CLI is missing in this container. Run on the Unraid host, or install docker CLI and mount /var/run/docker.sock into the container."
    fi
    die "Docker CLI is missing on host. Install Docker Engine/CLI and retry."
  fi

  if [[ "${runtime_context}" = "container" && ! -S "/var/run/docker.sock" ]]; then
    die "Docker socket /var/run/docker.sock is not available in this container. Run on host or mount the Docker socket."
  fi

  if ! docker info >/dev/null 2>&1; then
    if [[ "${runtime_context}" = "container" ]]; then
      die "Docker daemon is unreachable from this container. Ensure /var/run/docker.sock is mounted with correct permissions, or run on host."
    fi
    die "Docker daemon is not reachable. Start Docker and retry."
  fi
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

split_image_ref() {
  local ref="$1"
  if [[ "${ref##*/}" == *:* ]]; then
    IMAGE_REPO="${ref%:*}"
    IMAGE_TAG="${ref##*:}"
  else
    IMAGE_REPO="${ref}"
    IMAGE_TAG="latest"
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
  local current="$1"
  local bump_kind="$2"

  parse_semver "${current}" || return 1

  local major="${SEMVER_MAJOR}"
  local minor="${SEMVER_MINOR}"
  local patch="${SEMVER_PATCH}"

  case "${bump_kind}" in
    major)
      major=$((major + 1))
      minor=0
      patch=0
      ;;
    minor)
      minor=$((minor + 1))
      patch=0
      ;;
    patch)
      patch=$((patch + 1))
      ;;
    *)
      return 1
      ;;
  esac

  printf '%s.%s.%s\n' "${major}" "${minor}" "${patch}"
}

detect_auto_bump() {
  if ! command -v git >/dev/null 2>&1; then
    printf 'patch\n'
    return
  fi
  if ! git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'patch\n'
    return
  fi

  local last_semver_tag range subjects
  last_semver_tag="$(git -C "${REPO_ROOT}" tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-version:refname | head -n1 || true)"
  range="HEAD"
  if [[ -n "${last_semver_tag}" ]]; then
    range="${last_semver_tag}..HEAD"
  fi

  subjects="$(git -C "${REPO_ROOT}" log --pretty=%s ${range} 2>/dev/null || true)"

  # Check for breaking changes first (highest priority → major bump)
  if [[ -n "${subjects}" ]] && grep -qiE '(BREAKING CHANGE)|(^[a-z]+(\([^)]+\))?!:)' <<<"${subjects}"; then
    printf 'major\n'
  # Check for feature commits → minor bump
  elif [[ -n "${subjects}" ]] && grep -qiE '(^feat(\(.+\))?:)|(^feature(\(.+\))?:)' <<<"${subjects}"; then
    printf 'minor\n'
  else
    printf 'patch\n'
  fi
}

update_env_image() {
  local env_file="$1"
  local image="$2"
  local tmp_file

  tmp_file="$(mktemp)"
  awk -v image="${image}" '
    BEGIN { updated = 0 }
    /^[[:space:]]*TESSITURE_IMAGE=/ {
      print "TESSITURE_IMAGE=" image
      updated = 1
      next
    }
    { print }
    END {
      if (updated == 0) {
        print "TESSITURE_IMAGE=" image
      }
    }
  ' "${env_file}" > "${tmp_file}"
  mv "${tmp_file}" "${env_file}"
}

write_release_version_file() {
  local version="$1"
  printf '%s\n' "${version}" > "${RELEASE_VERSION_FILE}"
  log "Wrote canonical release version to ${RELEASE_VERSION_FILE}: ${version}"
}

clear_release_version_file() {
  if [[ -f "${RELEASE_VERSION_FILE}" ]]; then
    rm -f "${RELEASE_VERSION_FILE}"
    log "No semantic release version resolved; removed stale ${RELEASE_VERSION_FILE}"
  else
    log "No semantic release version resolved; ${RELEASE_VERSION_FILE} was not written"
  fi
}

git_tag_release() {
  local version="$1"
  local tag="v${version}"

  if [[ "${NO_GIT_TAG}" -eq 1 ]]; then
    log "Skipping git tag (--no-git-tag)"
    return
  fi

  if ! command -v git >/dev/null 2>&1; then
    log "WARNING: git not available; skipping release tag ${tag}"
    return
  fi

  if ! git -C "${REPO_ROOT}" rev-parse --git-dir >/dev/null 2>&1; then
    log "WARNING: not inside a git repository; skipping release tag ${tag}"
    return
  fi

  if git -C "${REPO_ROOT}" tag --list "${tag}" | grep -q "^${tag}$"; then
    log "Tag ${tag} already exists; skipping"
    return
  fi

  git -C "${REPO_ROOT}" tag -a "${tag}" -m "Release ${tag}"
  log "Tagged release: ${tag}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      [[ $# -ge 2 ]] || die "Missing value for --image"
      IMAGE="$2"
      IMAGE_SET=1
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
    --no-git-tag)
      NO_GIT_TAG=1
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

LATEST_IMAGE=""
if [[ "${VERSION_BUMP}" != "none" ]]; then
  current_version=""
  if parse_semver "${IMAGE_TAG}"; then
    current_version="${SEMVER_MAJOR}.${SEMVER_MINOR}.${SEMVER_PATCH}"
  else
    current_version="${BASE_VERSION}"
    log "Current image tag '${IMAGE_TAG}' is not semantic; using base version ${current_version}"
  fi

  EFFECTIVE_BUMP="${VERSION_BUMP}"
  if [[ "${VERSION_BUMP}" = "auto" ]]; then
    EFFECTIVE_BUMP="$(detect_auto_bump)"
  fi

  NEXT_VERSION="$(bump_semver "${current_version}" "${EFFECTIVE_BUMP}")" || die "Unable to bump version"
  IMAGE="${IMAGE_REPO}:${NEXT_VERSION}"
  LATEST_IMAGE="${IMAGE_REPO}:latest"
  RELEASE_VERSION="${NEXT_VERSION}"

  log "Version bump strategy: ${VERSION_BUMP} (effective=${EFFECTIVE_BUMP})"
  log "Version: ${current_version} -> ${NEXT_VERSION}"
else
  if parse_semver "${IMAGE_TAG}"; then
    RELEASE_VERSION="${SEMVER_MAJOR}.${SEMVER_MINOR}.${SEMVER_PATCH}"
    log "Version bump strategy: none (effective=none)"
    log "Using semantic image tag for release metadata: ${RELEASE_VERSION}"
  else
    log "Version bump strategy: none (effective=none)"
    log "Image tag '${IMAGE_TAG}' is not semantic; canonical release version will not be written"
  fi
fi

if [[ "${PUSH}" -eq 1 && "${IMAGE}" != */* ]]; then
  die "--push requires a registry-qualified image tag (example: ghcr.io/<org>/tessiture:<tag>)"
fi

log "Repository root: ${REPO_ROOT}"
log "Building image: ${IMAGE}"

BUILD_CMD=(docker build -t "${IMAGE}")
if [[ -n "${RELEASE_VERSION}" ]]; then
  BUILD_CMD+=(--build-arg "VITE_APP_VERSION=${RELEASE_VERSION}")
  log "Injecting frontend release metadata: VITE_APP_VERSION=${RELEASE_VERSION}"
fi
if [[ -n "${LATEST_IMAGE}" && "${LATEST_IMAGE}" != "${IMAGE}" ]]; then
  BUILD_CMD+=(-t "${LATEST_IMAGE}")
  log "Also tagging: ${LATEST_IMAGE}"
fi
BUILD_CMD+=("${REPO_ROOT}")
"${BUILD_CMD[@]}"

if [[ "${PUSH}" -eq 1 ]]; then
  log "Pushing image: ${IMAGE}"
  docker push "${IMAGE}"
  if [[ -n "${LATEST_IMAGE}" && "${LATEST_IMAGE}" != "${IMAGE}" ]]; then
    log "Pushing image: ${LATEST_IMAGE}"
    docker push "${LATEST_IMAGE}"
  fi
fi

if [[ -n "${ENV_FILE}" && "${VERSION_BUMP}" != "none" ]]; then
  update_env_image "${ENV_FILE}" "${IMAGE}"
  log "Updated ${ENV_FILE} with TESSITURE_IMAGE=${IMAGE}"
fi

if [[ -n "${RELEASE_VERSION}" ]]; then
  write_release_version_file "${RELEASE_VERSION}"
else
  clear_release_version_file
fi

# Tag the release in git after successful build and version file write
if [[ "${VERSION_BUMP}" != "none" && -n "${RELEASE_VERSION}" ]]; then
  git_tag_release "${RELEASE_VERSION}"
fi

IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${IMAGE}" 2>/dev/null || true)"
if [[ -n "${IMAGE_ID}" ]]; then
  log "Build complete: ${IMAGE} (${IMAGE_ID})"
else
  log "Build complete: ${IMAGE}"
fi
