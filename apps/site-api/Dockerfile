# Build context is the repository root (uv workspace requires sibling packages).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
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
COPY packages/python/site-domain packages/python/site-domain
COPY apps/site-api apps/site-api

RUN --mount=type=cache,target=/root/.cache/uv uv sync --package site-api --no-dev

COPY migrations migrations

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /workspace
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "site_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
