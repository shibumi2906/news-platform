# News Platform

Monorepo for two independently installable templates — a news **integrator**
and a news **site** — described in `docs/`. See `docs/00_INDEX.md` for the
full documentation map and `docs/21_IMPLEMENTATION_PLAN.md` for the build
sequence.

## Current stage

**AI Core and multilingual vertical slice.** The repository includes source
ingestion, Site editorial workflow and a provider-neutral AI path:
database-managed topics and prompts → relevance → fact/entity extraction →
event clustering → versioned article draft → language detection and configured
translations → signed Site ingestion. The seeded 16-language catalog, target
languages and terminology are managed in PostgreSQL through Integrator Admin
API. Original and translated versions remain separate and translations are
linked to the exact source `ArticleVersion`. Drafts enter editorial review and
are never auto-published. Media generation and the public web remain out of
scope.

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

This starts two isolated PostgreSQL databases, Redis, MinIO, applies both
Alembic migrations, and starts the two APIs plus Stage 1B workers. Source and
connection records still need operator provisioning; Stage 1B has no admin UI.
Health checks:

```text
GET http://localhost:8001/health/live
GET http://localhost:8001/health/ready
GET http://localhost:8002/health/live
GET http://localhost:8002/health/ready
```

## Repository layout

See `docs/23_REPOSITORY_STRUCTURE.md` for the target full-product tree.
See `docs/28_STAGE_1B_STATUS.md` for implemented scope and exclusions.
