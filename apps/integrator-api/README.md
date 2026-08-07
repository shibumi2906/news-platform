# Integrator API

Integrator Admin API provides health checks, Source management and AI Core
configuration.

- `/api/v1/sources` manages source adapters and source state.
- `/api/v1/ai/topics` manages database-backed topics, categories,
  subcategories, keywords, exclusions, regions, priority and relevance rules.
- `/api/v1/ai/prompts` creates immutable prompt versions and exposes only
  non-sensitive prompt metadata in list responses.

## Run locally

```bash
uv run --package integrator-api uvicorn integrator_api.main:create_app --factory --reload --app-dir apps/integrator-api/src
```

Requires `INSTANCE_ID`, `INSTANCE_TYPE` and `DATABASE_URL` in the environment.
