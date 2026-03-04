# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
ARG VITE_APP_VERSION
ENV VITE_APP_VERSION=${VITE_APP_VERSION}
COPY frontend/package.json ./package.json
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TESSITURE_HOST=0.0.0.0 \
    TESSITURE_PORT=8000 \
    TESSITURE_UPLOAD_DIR=/data/uploads \
    TESSITURE_OUTPUT_DIR=/data/outputs \
    TESSITURE_EXAMPLES_DIR=/app/examples/tracks \
    TESSITURE_FRONTEND_DIST=/app/frontend/dist \
    TESSITURE_STEM_CACHE_DIR=/data/stem_cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 python3.11-dev python3-pip \
        libsndfile1 ffmpeg \
    && ln -sf python3.11 /usr/bin/python \
    && ln -sf python3.11 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

# Install PyTorch with CUDA support first (separate index), then remaining deps
RUN python -m pip install --upgrade pip \
    && python -m pip install torch==2.2.2 torchaudio==2.2.2 \
       --index-url https://download.pytorch.org/whl/cu121 \
    && python -m pip install demucs==4.0.1 \
    && python -m pip install -r requirements.txt

# Pre-download Demucs model weights so they're baked into the image
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

COPY analysis/ ./analysis/
COPY api/ ./api/
COPY calibration/ ./calibration/
COPY reporting/ ./reporting/
COPY examples/ ./examples/
COPY README.md ./README.md
COPY pyproject.toml ./pyproject.toml

COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p /data/uploads /data/outputs

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.server:app --host ${TESSITURE_HOST:-0.0.0.0} --port ${TESSITURE_PORT:-8000}"]
