# processing-worker

Turns `source_material.ingested` outbox events into `CanonicalNewsPackage`
rows (docs/04_DATA_MODEL.md §3, docs/14_PUBLIC_AND_INTERNAL_API.md §4).

## Scope reduction (Stage 1B, explicitly approved)

No AI processing step exists yet (`docs/07_AI_PROCESSING_PIPELINE.md` is out
of scope until Stage 1C). `content` is copied straight from the RSS-derived
`SourceMaterial`; `facts`, `entities`, `taxonomy` and `media` are empty.
`package_version` is always `1` — re-processing is not yet possible because
there is no editorial/correction flow feeding back into the integrator.

## Pipeline

A Celery beat task (`process_pending_events`) polls `outbox_event` rows with
`status = "pending"` and `event_type = "source_material.ingested"`, in
batches of `PROCESSING_WORKER_BATCH_SIZE`. For each row, in a single DB
transaction (ADR-006):

1. loads the `SourceMaterial` and `Event` referenced in the outbox payload;
2. skips (marks `processed`, does not duplicate) if a `CanonicalNewsPackage`
   already exists for that `event_id` — the idempotency guard that makes
   re-running a batch after a partial failure safe;
3. otherwise builds a `contracts.package.CanonicalNewsPackageEnvelope`,
   persists it as a `CanonicalNewsPackage` row, and writes a new
   `canonical_news_package.created` outbox event for the delivery-worker;
4. marks the original outbox row `processed` (or `failed`, if the
   referenced material/event is missing).

Stage 1B runs a single poller instance, so rows are claimed with a plain
`SELECT` rather than `SELECT ... FOR UPDATE SKIP LOCKED` (see
`processing.py`).

## Running

```bash
celery -A processing_worker.celery_app worker --loglevel=info
celery -A processing_worker.celery_app beat --loglevel=info
```

## Configuration

In addition to `common.config.BaseAppSettings`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROCESSING_WORKER_POLL_INTERVAL_SECONDS` | `15.0` | Celery beat interval for `process_pending_events` |
| `PROCESSING_WORKER_BATCH_SIZE` | `50` | Max outbox rows processed per batch |

## Tests

```bash
uv run pytest services/processing-worker
```
