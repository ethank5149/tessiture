.DEFAULT_GOAL := help

PYTHON              ?= python3
NPM                 ?= npm
VENV_DIR            ?= .venv
VENV_PYTHON         ?= $(VENV_DIR)/bin/python3.12
VENV_PIP            ?= $(VENV_DIR)/bin/pip
VERSION_BUMP        ?= auto
BASE_VERSION        ?= 0.0.0
IMAGE               ?=
ENV_FILE            ?= deploy/.env
COMPOSE_FILE        ?= deploy/docker-compose.yml
RELEASE_VERSION_FILE ?= .release-version

.PHONY: help install install-dev test lint format typecheck run-api run-frontend build-frontend \
        build build-push deploy release tag \
        unraid-build unraid-build-push unraid-deploy unraid-one-shot \
        clean

# ─── Help ────────────────────────────────────────────────────────────────────

help:
	@printf '\n'
	@printf '  \033[1mTessiture — available make targets\033[0m\n'
	@printf '\n'
	@printf '  \033[4mDevelopment\033[0m\n'
	@printf '    %-22s %s\n' install          'Install runtime Python dependencies'
	@printf '    %-22s %s\n' install-dev      'Install runtime + dev Python dependencies into .venv'
	@printf '    %-22s %s\n' test             'Run backend tests (pytest)'
	@printf '    %-22s %s\n' lint             'Run ruff lint checks'
	@printf '    %-22s %s\n' format           'Run black formatting'
	@printf '    %-22s %s\n' typecheck        'Run mypy type checks'
	@printf '    %-22s %s\n' run-api          'Start FastAPI dev server'
	@printf '    %-22s %s\n' run-frontend     'Start Vite frontend dev server'
	@printf '    %-22s %s\n' build-frontend   'Build frontend assets (reads .release-version if present)'
	@printf '\n'
	@printf '  \033[4mBuild / Deploy\033[0m\n'
	@printf '    %-22s %s\n' build            'Build Docker image with semver bump (use: make build)'
	@printf '    %-22s %s\n' build-push       'Build and push image to registry'
	@printf '    %-22s %s\n' deploy           'Deploy compose stack via deploy/scripts/deploy.sh'
	@printf '    %-22s %s\n' release          'Build + deploy + verify (one-shot; primary release target)'
	@printf '    %-22s %s\n' tag              'Re-tag current version in git without rebuilding'
	@printf '\n'
	@printf '  \033[4mMaintenance\033[0m\n'
	@printf '    %-22s %s\n' clean            'Remove common local build artifacts'
	@printf '\n'
	@printf '  \033[4mVariables\033[0m\n'
	@printf '    %-22s %s\n' 'IMAGE=<reg/repo[:tag]>' 'Docker image (optional; read from ENV_FILE if unset)'
	@printf '    %-22s %s\n' 'VERSION_BUMP=auto|patch|minor|major|none' '(default: auto)'
	@printf '    %-22s %s\n' 'BASE_VERSION=x.y.z'     '(default: 0.0.0)'
	@printf '    %-22s %s\n' 'ENV_FILE=deploy/.env'   'Env file for build/deploy'
	@printf '    %-22s %s\n' 'COMPOSE_FILE=deploy/docker-compose.yml' 'Compose file for deploy'
	@printf '\n'

# ─── Development ─────────────────────────────────────────────────────────────

install:
	$(VENV_PIP) install -r requirements.txt

install-dev:
	mkdir -p $(VENV_DIR)
	$(VENV_PYTHON) -m venv $(VENV_DIR)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt
	$(VENV_PIP) install \
		pytest==8.3.5 \
		pytest-asyncio==0.25.3 \
		httpx==0.28.1 \
		black==24.10.0 \
		mypy==1.15.0 \
		ruff==0.9.10

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m black .

typecheck:
	$(PYTHON) -m mypy .

run-api:
	@if [ -x "$(VENV_PYTHON)" ]; then \
		echo "Using virtualenv Python: $(VENV_PYTHON)"; \
		$(VENV_PYTHON) -m uvicorn api.server:app --host 0.0.0.0 --port 8000; \
	else \
		echo "Using system Python: $(PYTHON)"; \
		$(PYTHON) -m uvicorn api.server:app --host 0.0.0.0 --port 8000; \
	fi

run-frontend:
	cd frontend && $(NPM) install && $(NPM) run dev

build-frontend:
	@if [ -f "$(RELEASE_VERSION_FILE)" ] && grep -Eq '^v?[0-9]+\.[0-9]+\.[0-9]+$$' "$(RELEASE_VERSION_FILE)"; then \
		APP_VERSION="$$(tr -d '[:space:]' < $(RELEASE_VERSION_FILE))"; \
		APP_VERSION="$${APP_VERSION#v}"; \
		echo "Using VITE_APP_VERSION=$${APP_VERSION} from $(RELEASE_VERSION_FILE)"; \
		cd frontend && VITE_APP_VERSION=$${APP_VERSION} $(NPM) install && VITE_APP_VERSION=$${APP_VERSION} $(NPM) run build; \
	else \
		cd frontend && $(NPM) install && $(NPM) run build; \
	fi

# ─── Build / Deploy ──────────────────────────────────────────────────────────

build:
	deploy/scripts/build.sh \
		$(if $(IMAGE),--image $(IMAGE)) \
		--env-file $(ENV_FILE) \
		--version-bump $(VERSION_BUMP) \
		--base-version $(BASE_VERSION)

build-push:
	deploy/scripts/build.sh \
		$(if $(IMAGE),--image $(IMAGE)) \
		--env-file $(ENV_FILE) \
		--version-bump $(VERSION_BUMP) \
		--base-version $(BASE_VERSION) \
		--push

deploy:
	deploy/scripts/deploy.sh \
		--env-file $(ENV_FILE) \
		--compose-file $(COMPOSE_FILE)

release:
	deploy/scripts/one-shot.sh \
		$(if $(IMAGE),--image $(IMAGE)) \
		--env-file $(ENV_FILE) \
		--compose-file $(COMPOSE_FILE) \
		--version-bump $(VERSION_BUMP) \
		--base-version $(BASE_VERSION)

tag:
	deploy/scripts/build.sh \
		$(if $(IMAGE),--image $(IMAGE)) \
		--env-file $(ENV_FILE) \
		--version-bump none

# ─── Deprecated aliases (kept for backward compatibility) ────────────────────

unraid-build: build
	@echo '[deprecated] Use: make build'

unraid-build-push: build-push
	@echo '[deprecated] Use: make build-push'

unraid-deploy: deploy
	@echo '[deprecated] Use: make deploy'

unraid-one-shot: release
	@echo '[deprecated] Use: make release'

# ─── Maintenance ─────────────────────────────────────────────────────────────

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache frontend/node_modules frontend/dist
