# Integrator API

Integrator Admin API provides health checks, Source management and AI Core
configuration.

- `/api/v1/sources` manages source adapters and source state.
- `/api/v1/ai/topics` manages database-backed topics, categories,
  subcategories, keywords, exclusions, regions, priority and relevance rules.
- `/api/v1/ai/prompts` creates immutable prompt versions and exposes only
  non-sensitive prompt metadata in list responses.
- `/api/v1/ai/languages` manages the seeded, configurable 16-language catalog,
  target-translation flags, priority and RTL/LTR direction.
- `/api/v1/ai/terminology` manages source/target glossary entries. Terminology
  values are never included in structured logs.

## Run locally

```bash
uv run --package integrator-api uvicorn integrator_api.main:create_app --factory --reload --app-dir apps/integrator-api/src
```

Requires `INSTANCE_ID`, `INSTANCE_TYPE` and `DATABASE_URL` in the environment.
