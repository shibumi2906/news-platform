# Production hardening runbook

## Security model

Administrative users, roles, permissions, sessions, audit records and secret
revision metadata live in the Site PostgreSQL database. Passwords use salted
scrypt. Session tokens are signed with an active `kid:secret` key and persisted
only as SHA-256 hashes. `ADMIN_SESSION_KEYS` accepts comma-separated keys; place
the new key first during an overlap window, then retire the previous key after
all old sessions have expired. The same key ring is injected into both APIs.

Unsafe session-authenticated requests require the opaque HttpOnly session plus a
double-submit CSRF token. Trusted hosts, explicit origins, strict cookies,
sliding idle expiry and login throttling are enforced. Service tokens accept a
comma-separated overlap window for machine-to-machine rotation and must never be
made available to the public web container. The Integrator API validates every
signed administrator session and unsafe-request CSRF token against the Site-owned
session store through a fail-closed internal introspection call, so logout,
deactivation and RBAC changes take effect immediately. OIDC and MFA are extension
protocols; local passwords are the implemented identity provider in this release. Enabling
`mfa_required` blocks local login until an MFA verifier/enrollment flow is wired.
Bootstrap credentials are an install-time pair only: remove both variables after
the first administrator has been created; subsequent starts do not require them.

The audit API is read-only and PostgreSQL rejects updates or deletes through an
append-only trigger. Logs contain identifiers and bounded diagnostics, not
credentials, source/article bodies, provider payloads, or personal profile data.

## Observability and reliability

Both APIs expose `/health/live`, `/health/ready`, `/metrics`, a validated
`X-Request-Id`, and W3C `traceparent`. Production readiness verifies PostgreSQL,
Redis and, on Site, S3/MinIO. Monitoring contracts are in
`deploy/monitoring/alerts.yml` and `deploy/monitoring/dashboard.json`.

Distribution schedules create a provider-neutral `background_job`. Workers claim
a bounded lease before external I/O; expired leases are recoverable after a crash.
Every attempt is retained. Exhausted retryable work creates a dead letter that an
operator can inspect and explicitly replay. Provider-side idempotency remains the
final protection for the ambiguous crash window after an external success and
before the local commit.

## Installation and updates

Validate secrets without printing them, then use the production overlay:

```powershell
./scripts/validate-production-env.ps1
./scripts/deploy.ps1 -Action install
./scripts/deploy.ps1 -Action update
./scripts/deploy.ps1 -Action rollback -RollbackCompose D:\releases\previous-images.yml
```

The overlay requires explicit PostgreSQL, Redis, MinIO, session, service-token,
allowed-host and web-origin values; bootstrap-admin values are a complete optional
pair after initial installation. Store secrets in the platform's secret manager;
do not commit `.env` files. Application rollback fails closed
unless `-RollbackCompose` names an operator-controlled override containing the
previous immutable image references. Database downgrade is deliberately opt-in with
`-RollbackDatabase` and should only follow a tested backup and migration-specific
compatibility review.

## Backup and restore

`scripts/backup.ps1` creates PostgreSQL custom-format dumps, an object-storage
archive and a SHA-256 manifest. Copy the resulting directory to encrypted,
off-host storage with retention and access controls.

Restore is destructive and requires both an explicit target and
`-ConfirmRestore`:

```powershell
./scripts/restore.ps1 -BackupDirectory D:\secure\backup -Stamp 20260807T120000Z -ConfirmRestore
```

Always restore into an isolated environment first, apply migrations, verify
checksums, readiness, object retrieval and editorial smoke tests, and only then
approve production recovery. PostgreSQL and MinIO backups are not transactionally
atomic with one another; the manifest timestamp defines the recovery set.

## Release gates

Required gates are full pytest (including PostgreSQL/Redis/MinIO E2E), mypy,
Ruff, frontend tests/typecheck/build, accessibility source contracts, Alembic
upgrade from empty databases, performance smoke, clean production-like Compose,
backup/restore rehearsal and application/database rollback rehearsal.
