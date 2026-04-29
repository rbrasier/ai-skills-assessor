# syntax=docker/dockerfile:1.6
#
# AI Skills Assessor — voice-engine image (Phase 3, v0.4.0).
#
# Two-stage build:
#   1. `builder` — installs the full `[voice]` extras (Pipecat, asyncpg,
#                  pgvector, Anthropic SDK) into a virtualenv.
#   2. `runtime` — copies the venv + source; runs uvicorn as `appuser`
#                  (non-root) with a deep `/health` healthcheck so
#                  Railway can automatically roll back bad deploys.
#
# Build context: `apps/voice-engine/` (the repo root is not required).
#   docker build -f apps/voice-engine/Dockerfile apps/voice-engine

ARG PYTHON_VERSION=3.11-slim

# ─── Stage 1: builder ─────────────────────────────────────────────
FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# Build-time deps for asyncpg / pgvector / pipecat native wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libffi-dev \
      curl \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV"

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --upgrade pip \
 && pip install -e ".[voice]"

# ─── Stage 2: runtime ─────────────────────────────────────────────
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    LOG_LEVEL=INFO \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      tini \
 && rm -rf /var/lib/apt/lists/* \
 && addgroup --system --gid 1001 appgroup \
 && adduser  --system --uid 1001 --ingroup appgroup appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appgroup /app      /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl --fail --silent "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]
