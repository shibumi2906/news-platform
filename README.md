# News Platform

Monorepo for two independently installable templates — a news **integrator**
and a news **site** — described in `docs/`. See `docs/00_INDEX.md` for the
full documentation map and `docs/21_IMPLEMENTATION_PLAN.md` for the build
sequence.

## Current stage

**Stage 1A — Repository Foundation.** This stage contains only shared
infrastructure scaffolding: workspace tooling, the `common` package
(config, logging, errors, ids, time, db, outbox interface) and bare
FastAPI skeletons for `integrator-api` and `site-api` with liveness/readiness
health checks. It intentionally contains **no domain logic, no business
endpoints and no domain database tables**. Those are added in Stage 1B
(the RSS → Incoming Package vertical).

Logging is centralized in `packages/python/common` (see its README): JSON
lines on stdout only, level via `LOG_LEVEL`, correlation-id propagation via
`ContextVar`, no file sinks — see `packages/python/common/README.md`.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker and Docker Compose

## Local development

```bash
# install workspace dependencies
uv sync

# static checks
uv run ruff check .
uv run mypy .

# unit tests
uv run pytest
```

## Running the dev stack

```bash
docker compose -f deploy/compose/docker-compose.dev.yml up --build
```

This starts two isolated PostgreSQL databases (integrator, site), Redis,
MinIO and the two API skeletons. Health checks:

```text
GET http://localhost:8001/health/live
GET http://localhost:8001/health/ready
GET http://localhost:8002/health/live
GET http://localhost:8002/health/ready
```

## Repository layout

See `docs/23_REPOSITORY_STRUCTURE.md` for the target full-product tree.
Stage 1A only populates the subset needed to run the shared foundation.
