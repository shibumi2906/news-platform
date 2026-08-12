# source-worker

RSS/Atom, configuration-driven HTML, and JSON HTTP API source connectors
(docs/05_SOURCE_CONNECTORS.md).

## Pipeline

1. **discover** — `poll_all_active_sources` selects every active `Source`
   row and enqueues one `poll_source` task per source.
2. **fetch** — `fetcher.fetch_feed` performs HTTP GET with redirects,
   (`If-None-Match`/`If-Modified-Since`), with a bounded retry that honors
   `Retry-After` on `429`/`5xx` (docs/05 §3).
3. **normalize** — RSS turns feed entries into
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

HTML sources use `config` with `item_selector`, `url_selector`,
`title_selector`, and `content_selector`; optional `canonical_selector`,
`published_at_selector`, `published_at_attribute`, `author_selector`, and
`language` refine extraction. Selectors support tag, `.class`, `#id`, `[attr]`,
`[attr=value]`, descendants and comma groups. The connector does not use a
browser and never hardcodes a site-specific parser.

API sources use `config.items_path` and `config.mapping` (`id`, `title`, and
`url` are required; `published_at`, `author`, `content`, `summary`, and
`language` are optional). `method`, `query_params`, `headers`, `json_body`, and
page/cursor-style `pagination` are configured per source. Set `auth_env` to an
environment-variable name and optionally `auth_header`/`auth_prefix`; the secret
value is never stored in PostgreSQL. OAuth and provider-specific adapters are
not part of this connector.

## Scope reductions

- No API/browser/search adapters; Playwright/Selenium are deliberately not a fallback.
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
