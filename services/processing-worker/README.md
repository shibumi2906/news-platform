# processing-worker

Turns `source_material.ingested` events into classified, extracted and
clustered AI drafts. Provider calls are routed through a provider-neutral
gateway; local development and tests use a deterministic fake provider.

## Pipeline

A Celery beat task polls pending source-material outbox events. For each row:

1. load active topics and versioned prompts from PostgreSQL;
2. run relevance and store score/reason for every returned topic;
3. extract facts/entities and cluster semantically equivalent materials;
4. generate a versioned draft package from all event sources;
5. store AI telemetry and source/fact provenance, then emit
   `canonical_news_package.created` for delivery to Site ingestion.

Source text, AI output and configuration secrets are not written to logs.
Logs contain operation, provider/model, token counts, latency, cost and opaque
identifiers only. AI packages enter Site as editorial drafts and are never
automatically published.

## Running

```bash
celery -A processing_worker.celery_app worker --loglevel=info
celery -A processing_worker.celery_app beat --loglevel=info
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROCESSING_WORKER_POLL_INTERVAL_SECONDS` | `15.0` | Celery beat interval |
| `PROCESSING_WORKER_BATCH_SIZE` | `50` | Maximum outbox rows per batch |
| `AI_PROVIDERS` | `fake` | Ordered comma-separated provider adapter names |
| `AI_MAX_ATTEMPTS_PER_PROVIDER` | `2` | Bounded attempts before fallback |

## Tests

```bash
uv run pytest services/processing-worker
```
