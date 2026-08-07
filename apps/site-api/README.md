# Site API

Stage 1A skeleton only: FastAPI app factory, config wiring and
liveness/readiness health checks. No business endpoints or domain tables —
those are added in Stage 1B (`docs/02_SYSTEM_ARCHITECTURE.md` §5.2).

## Run locally

```bash
uv run --package site-api uvicorn site_api.main:create_app --factory --reload --app-dir apps/site-api/src
```

Requires `INSTANCE_ID`, `INSTANCE_TYPE`, `DATABASE_URL` in the environment
(see root `.env.example`).

Public read models are under `/api/v1/public`; Site Admin read models are under
`/api/v1/admin`. When `ADMIN_API_TOKEN` is configured, editorial and admin
routes require the matching `X-Admin-Token` supplied by the Next.js BFF.
