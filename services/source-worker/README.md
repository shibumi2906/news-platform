# source-worker

RSS/Atom source connector (docs/05_SOURCE_CONNECTORS.md). Implements the
`discover -> fetch -> normalize -> checkpoint` pipeline for the RSS/Atom
adapter type only — other adapter types (HTML, browser, search) are out of
scope for Stage 1B.

## Pipeline

1. **discover** — `poll_all_active_sources` selects every active `Source`
   row and enqueues one `poll_source` task per source.
2. **fetch** — `fetcher.fetch_feed` performs a conditional HTTP GET
   (`If-None-Match`/`If-Modified-Since`), with a bounded retry that honors
   `Retry-After` on `429`/`5xx` (docs/05 §3).
3. **normalize** — `rss.parse_rss_feed` turns feed entries into
   `contracts.source.SourceCandidate` values. Malformed entries (missing
   link) are skipped rather than failing the whole poll.
4. **checkpoint** — `ingestion.ingest_candidates` persists each candidate as
   a `SourceMaterial` row, deduplicated on `(source_id, external_id)` and
   `(source_id, canonical_url_hash)` (docs/04_DATA_MODEL.md §3). New
   materials also get a 1:1 `Event` stub and a `source_material.ingested`
   `OutboxEvent` row, written in the same DB transaction (ADR-006).

The RSS adapter itself never writes an `Event` or article
(docs/05_SOURCE_CONNECTORS.md §2) — that happens one layer up, in
`ingestion.py`.

## Scope reductions (Stage 1B, explicitly approved)

- RSS/Atom only; no HTML/browser/search adapters yet.
- Every `SourceMaterial` gets its own 1:1 `Event` stub; multi-source event
  clustering is out of scope until AI processing is introduced.

## Running

Celery + Redis (OD-01). Two processes share this image:

```bash
celery -A source_worker.celery_app worker --loglevel=info
celery -A source_worker.celery_app beat --loglevel=info
```

## Configuration

In addition to `common.config.BaseAppSettings` (`DATABASE_URL`,
`REDIS_URL`, `LOG_LEVEL`, ...):

| Variable | Default | Purpose |
| --- | --- | --- |
| `SOURCE_WORKER_HTTP_TIMEOUT_SECONDS` | `10.0` | Per-request HTTP timeout |
| `SOURCE_WORKER_USER_AGENT` | `news-platform-source-worker/0.1` | HTTP `User-Agent` |
| `SOURCE_WORKER_MAX_CANDIDATES_PER_POLL` | `200` | Cap on candidates ingested per poll |
| `SOURCE_WORKER_POLL_INTERVAL_SECONDS` | `300.0` | Celery beat interval for `poll_all_active_sources` |

## Tests

Fixtures only — no network calls (docs/05 §6):

```bash
uv run pytest services/source-worker
```
