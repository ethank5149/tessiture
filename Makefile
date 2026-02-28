PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
NPM ?= npm
VENV_DIR ?= .venv
VENV_PYTHON ?= $(VENV_DIR)/bin/python3
VENV_PIP ?= $(VENV_PYTHON) -m pip

.PHONY: help install install-dev test lint format typecheck run-api run-frontend build-frontend docker-build docker-run-unraid unraid-build unraid-build-push unraid-deploy unraid-one-shot clean

help:
	@echo "Targets:"
	@echo "  install            Install runtime Python dependencies"
	@echo "  install-dev        Install runtime and development dependencies"
	@echo "  test               Run backend tests"
	@echo "  lint               Run ruff lint checks"
	@echo "  format             Run black formatting"
	@echo "  typecheck          Run mypy checks"
	@echo "  run-api            Start FastAPI server"
	@echo "  run-frontend       Start frontend dev server"
	@echo "  build-frontend     Build frontend assets"
	@echo "  docker-build       Build single-image Tessiture container"
	@echo "  docker-run-unraid  Run container with Unraid-style bind mounts"
	@echo "  unraid-build       Build Unraid image helper (default tessiture:local)"
	@echo "  unraid-build-push  Build and push image (set IMAGE=registry/repo:tag)"
	@echo "  unraid-deploy      Deploy Unraid compose stack via helper"
	@echo "  unraid-one-shot    Build + deploy + verify via helper"
	@echo "  clean              Remove common local artifacts"

install:
	$(PIP) install -r requirements.txt

install-dev:
	# Create venv directory if not exists
	mkdir -p $(VENV_DIR)
	$(VENV_PYTHON) -m venv $(VENV_DIR)
	# Upgrade pip
	$(VENV_PIP) install --upgrade pip
	# Install stable versions, per
	# https://packaging.python.org/en/latest/source_releases.html
	$(VENV_PIP) install -r requirements.txt
	# Install developer dependencies here instead of extras so setup succeeds
	# in a virtual env, i.e., allowing 'run-api' target to work locally
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
	cd frontend && $(NPM) install && $(NPM) run build

docker-build:
	docker build -t tessiture:latest .

docker-run-unraid:
	docker run --rm -p 8000:8000 \
		-e TESSITURE_HOST=0.0.0.0 \
		-e TESSITURE_PORT=8000 \
		-e TESSITURE_UPLOAD_DIR=/data/uploads \
		-e TESSITURE_OUTPUT_DIR=/data/outputs \
		-v /mnt/user/appdata/tessiture/uploads:/data/uploads \
		-v /mnt/user/appdata/tessiture/outputs:/data/outputs \
		tessiture:latest

unraid-build:
	bash deploy/unraid/scripts/build.sh $(if $(IMAGE),--image $(IMAGE),)

unraid-build-push:
	bash deploy/unraid/scripts/build.sh --image $(IMAGE) --push

unraid-deploy:
	bash deploy/unraid/scripts/deploy.sh

unraid-one-shot:
	bash deploy/unraid/scripts/one-shot.sh $(if $(IMAGE),--image $(IMAGE),)

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache frontend/node_modules frontend/dist
