# Build context is the repository root (uv workspace requires sibling packages).
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

RUN apt-get update && apt-get install -y --no-install-recommends curl procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/workspace/.venv/bin:${PATH}"

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY packages/python/common packages/python/common
COPY packages/python/contracts packages/python/contracts
COPY packages/python/integrator-domain packages/python/integrator-domain
COPY services/source-worker services/source-worker

RUN --mount=type=cache,target=/root/.cache/uv uv sync --package source-worker --no-dev
# The official image supplies Chromium and all required browser libraries.
# Keep the Python package version pinned to the matching image release.

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /workspace
USER appuser

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD celery -A source_worker.celery_app inspect ping -d "celery@$HOSTNAME" || exit 1

CMD ["celery", "-A", "source_worker.celery_app", "worker", "--loglevel=info"]
