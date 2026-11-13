# News Platform

Monorepo for two independently installable templates — a news **integrator**
and a news **site** — described in `docs/`. See `docs/00_INDEX.md` for the
full documentation map and `docs/21_IMPLEMENTATION_PLAN.md` for the build
sequence.

## Current stage

**Production Hardening.** The repository includes source
ingestion, Site editorial workflow and a provider-neutral AI path:
database-managed topics and prompts → relevance → fact/entity extraction →
event clustering → versioned article draft → language detection and configured
translations → signed Site ingestion. The seeded 16-language catalog, target
languages and terminology are managed in PostgreSQL through Integrator Admin
API. Original and translated versions remain separate and translations are
linked to the exact source `ArticleVersion`. Drafts enter editorial review and
are never auto-published. A Next.js App Router application exposes the
published Site read model, multilingual/RTL article rendering, SEO/RSS/sitemap,
and session-protected Integrator/Site administration. The Site media layer
stores originals and derivatives through an S3-compatible abstraction while
PostgreSQL retains metadata, rights, provenance, article/translation/event
links, generation telemetry, meme versions, and video storyboards. Image
generation is provider-neutral with a deterministic fake provider for tests.
Distribution uses immutable publication versions, scheduling, idempotency,
audited attempts, exponential retry and DLQ states. Telegram, Facebook,
Instagram, TikTok, X, and YouTube use provider-specific HTTP adapters with
capability checks; OAuth credentials are configured only through server-side
environment references. Production hardening adds database-backed users, RBAC,
rotatable signed admin sessions, CSRF protection, OIDC/MFA extension contracts,
append-only audit records, metrics and W3C trace context, unified jobs with
leases and manual DLQ replay, hardened health checks, production Compose,
backup/restore and controlled install/update/rollback tooling. Billing,
advertising and additional production social providers remain out of scope.

Logging is centralized in `packages/python/common` (see its README): JSON
lines on stdout only, level via `LOG_LEVEL`, correlation-id propagation via
`ContextVar`, no file sinks — see `packages/python/common/README.md`.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker and Docker Compose

## Deploying to a server

Follow the [first production deployment guide](docs/30_FIRST_PRODUCTION_DEPLOYMENT.md).
It covers server prerequisites, environment setup, HTTPS, administrator login,
the first Integrator → Site connection and verification through publication.
The bundled production stack uses Caddy, two PostgreSQL databases, Redis and
MinIO. It publishes ports 80 and 443. Integrator API stays on the Compose network.
Use the [production runbook](docs/29_PRODUCTION_HARDENING.md) for backups,
restore, updates and rollback.

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
Alembic migrations, and starts the two APIs, ingestion/AI/delivery/distribution
workers and Next.js application.
Open `http://localhost:3000`; development bootstrap credentials come from
`ADMIN_BOOTSTRAP_USERNAME`/`ADMIN_BOOTSTRAP_PASSWORD`. The browser receives an
opaque, HttpOnly Site API session; backend service tokens are not exposed to it.
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
See `docs/29_PRODUCTION_HARDENING.md` for production configuration, monitoring,
backup/restore, update and rollback procedures.
