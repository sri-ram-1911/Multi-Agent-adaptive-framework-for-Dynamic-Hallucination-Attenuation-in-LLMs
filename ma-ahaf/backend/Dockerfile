# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/data/models

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git && rm -rf /var/lib/apt/lists/*

# CPU-only torch first (keeps the image lean and the layer cached).
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2"

COPY . .
RUN pip install -e ".[dev]"

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=10 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
