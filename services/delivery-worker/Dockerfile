# Build context is the repository root (uv workspace requires sibling packages).
FROM python:3.12-slim

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
COPY services/delivery-worker services/delivery-worker

RUN --mount=type=cache,target=/root/.cache/uv uv sync --package delivery-worker --no-dev

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /workspace
USER appuser

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD celery -A delivery_worker.celery_app inspect ping -d "celery@$HOSTNAME" || exit 1

CMD ["celery", "-A", "delivery_worker.celery_app", "worker", "--loglevel=info"]
