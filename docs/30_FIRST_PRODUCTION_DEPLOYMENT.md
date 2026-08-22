# First production deployment checklist

This is the practical profile for one independent Site installation.  The
`INSTANCE_ID` is the tenant/site boundary: generate one UUID for the Site and a
different UUID for the Integrator. There is no shared cross-installation tenant
bootstrap table.

## Required configuration

| Area | Environment | Used by | Required | Missing behavior |
|---|---|---|---|---|
| Database | `POSTGRES_INTEGRATOR_PASSWORD`, `POSTGRES_SITE_PASSWORD` | Compose/migrations/APIs | yes | deployment validation fails |
| Queue | `REDIS_PASSWORD` | APIs/workers | yes | readiness fails |
| Storage | `MINIO_ROOT_*` or `S3_*`, `S3_BUCKET` | Site media | yes | Site readiness fails on bucket access |
| Edge | `API_ALLOWED_HOSTS`, `WEB_ORIGIN`, `NEXT_PUBLIC_WEB_URL` | APIs/web | yes | validation/startup rejects unsafe config |
| Admin | `ADMIN_API_TOKEN`, `ADMIN_SESSION_KEYS` | both APIs | yes | production startup rejects unsafe/missing values |
| First admin | `ADMIN_BOOTSTRAP_USERNAME`, `ADMIN_BOOTSTRAP_PASSWORD` | Site API | optional pair | no user is seeded; set both only for first start |
| AI | `AI_PROVIDERS`, provider key/model | processing workers | yes | production worker rejects fake/unconfigured provider |
| Distribution | `DISTRIBUTION_SECRET_*` | distribution worker | only enabled channel | channel remains unconfigured/fails closed |
| Dashboard | `SUPABASE_DASHBOARD_URL`, `SUPABASE_DASHBOARD_KEY` | Site API | optional pair | export is disabled |

Copy `.env.production.example` to the operator's secret manager (not Git).
SMTP/email is not an implemented runtime dependency; do not invent credentials
for it.

## Deployment sequence

1. Choose DNS names, create PostgreSQL databases/users, Redis, and S3/MinIO
   bucket/credentials. Generate separate Integrator/Site instance UUIDs.
2. Configure reverse proxy/TLS: HTTPS canonical host, forwarded headers,
   request size limits, security headers, and routes for Web, APIs and payment
   webhooks. Caddy is recommended pending OD-02.
3. Populate secrets from `.env.production.example`; run
   `./scripts/validate-production-env.ps1`.
4. Start with `./scripts/deploy.ps1 -Action install`. Migrations run before APIs.
5. First Site startup seeds the admin only when both `ADMIN_BOOTSTRAP_*` values
   are set. Log in, create roles/users, then remove both bootstrap variables.
6. Configure source connections, AI provider, optional social channels, payment
   provider after OD-09, and optional dashboard export.
7. Run `./scripts/smoke-production.ps1 -IntegratorUrl https://integrator.example.com -SiteApiUrl https://api.example.com -WebUrl https://www.example.com -AdminApiToken <service-token>`.

Application rollback uses immutable image overrides with `deploy.ps1 -Action
rollback -RollbackCompose <previous-images.yml>`. Database downgrade is opt-in
only after backup and migration compatibility review.

## First-launch decisions

| Decision | Options | Minimum first-launch choice | Can defer | Config affected |
|---|---|---|---|---|
| OD-01 queue | Redis/Celery profile or managed equivalent | Redis endpoint/password | scaling profile | `REDIS_*`, worker concurrency |
| OD-02 proxy | Caddy, Traefik, Nginx | TLS proxy and domains | proxy implementation change | hosts/origins/public URLs |
| OD-03 storage | MinIO or managed S3 | bucket, endpoint, credentials | CDN | `S3_*`/`MINIO_*` |
| OD-07 AI | installed OpenAI adapter/model policy | provider/model/key | extra adapters | `AI_*`, `OPENAI_*` |
| OD-08 analytics | disabled or dashboard endpoint | disabled is valid | vendor/retention | `SUPABASE_*` |
| OD-09 payments | provider/country/methods | leave unconfigured is valid | all payment setup | provider namespaced secrets/webhook |
| OD-10 operations | RPO/RTO/SLO/retention | backup destination and cadence | formal SLO | backup/monitoring policy |
| OD-11 capacity | small/medium/large profile | worker concurrency/resources | benchmark scaling | Compose overrides |
