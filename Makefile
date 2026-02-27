PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
NPM ?= npm

.PHONY: help install install-dev test lint format typecheck run-api run-frontend build-frontend docker-build docker-run-unraid clean

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
	@echo "  clean              Remove common local artifacts"

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements.txt
	$(PIP) install -e .[dev]

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m black .

typecheck:
	$(PYTHON) -m mypy .

run-api:
	$(PYTHON) -m uvicorn api.server:app --host 0.0.0.0 --port 8000

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

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache frontend/node_modules frontend/dist
