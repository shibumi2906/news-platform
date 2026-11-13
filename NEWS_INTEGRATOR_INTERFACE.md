# News Integrator Interface

This document defines the production interface between a News Integrator instance and a Site instance. It describes the contract implemented in this repository at schema version `1.1`, including lifecycle operations, replay, delivery safety, signing-key rotation, metadata provenance, and compatibility with `1.0` consumers.

## 1. System boundary

The Integrator owns source ingestion, normalization, AI-assisted extraction, clustering, canonical package versioning, and outbound delivery. A Site owns receipt validation, immutable incoming versions, editorial workflows, publication, and distribution.

PostgreSQL is authoritative on each side. Redis and Celery provide scheduling only. Integrator and Site databases remain independent and are connected exclusively through the signed HTTP contract.

## 2. Canonical package contract

The canonical schema is generated from `contracts.package.CanonicalNewsPackageEnvelope` into `packages/schemas/canonical_news_package.schema.json`.

Required identity fields are:

- `schema_version`
- `package_id`
- `package_version`
- `instance_id`
- `event_id`
- `content`
- `sources`

Schema `1.1` adds the following optional or defaulted fields without removing `1.0` fields:

- `operation`: `created`, `updated`, `corrected`, `retracted`, or `deleted`
- `revision_reason`
- `topics` and `categories`
- `geographies`
- typed `media`
- `ai_provenance`
- richer source provenance

`taxonomy` and `regions` remain present for legacy consumers. A `1.0` payload remains valid input. Receivers reject unsupported schema versions before persistence; this implementation accepts exactly `1.0` and `1.1`.

### 2.1 Version and lifecycle rules

`package_id` is the stable logical identity. `package_version` is a monotonically increasing positive integer. Every revision is inserted as a new immutable `CanonicalNewsPackage` row.

- Initial packaging emits `created`, version 1.
- Ordinary pipeline regeneration emits `updated`, version 2 or later.
- Operator corrections emit `corrected` and require replacement content plus a reason.
- Retractions emit `retracted` and require a reason.
- Deletions emit `deleted` and require a reason. This is a tombstone event; prior versions are retained.

The Site stores every accepted version in `IncomingPackageVersion`. `IncomingPackage.latest_version` advances only when the arriving version is greater, so late replay of an older version cannot regress the current view.

### 2.2 Content and languages

`content` is the canonical language variant and contains title, canonical URL, language, and optional excerpt/body. `language_versions` contains additional variants with their language and translation provenance.

### 2.3 Source provenance

Each source reference can include:

- stable source and source-material identifiers
- external identifier and source URL
- canonical URL and source name
- adapter type and author
- published and fetched timestamps
- SHA-256 content hash

The content hash is calculated from the normalized source URL, title, excerpt, and body. It supports traceability and change detection; it is not a rights assertion.

### 2.4 Topics, categories, and geography

`topics` and `categories` are typed records with name, optional slug, confidence, source, and source-material identity. `geographies` supports country, ISO country code, state/region, metro, city, and district, with confidence and extraction provenance.

The processing pipeline aggregates these records across all source material relevant to the event rather than exporting only the material that happened to trigger packaging.

### 2.5 Media

Media entries are typed as image or video and may contain source URL, thumbnail URL, MIME type, dimensions, duration, provider identifiers, source-material identity, rights hint, and attribution.

HTML ingestion captures Open Graph images. YouTube ingestion promotes provider metadata and the largest available thumbnail. `rights_hint` defaults to `link_only`; consumers must not interpret exported media as a license to copy or redistribute it.

### 2.6 AI provenance

`ai_provenance` links exported results to the AI operation, run, active/canary configuration release, prompt version, provider, and model. It covers relevant draft, relevance, extraction, geography, translation, and detection runs.

## 3. AI quality configuration at runtime

The processing worker resolves the active quality release for the requested operation at execution time. A release selects prompt versions and provider/model configuration. Canary routing uses a stable SHA-256 bucket of operation plus input, making assignment repeatable for the same work item.

When an operation has a quality policy but no active or canary release, processing fails closed with `no_active_release`. Installations with no quality policy continue through the legacy environment-configured provider route for migration compatibility and emit a route warning.

Budget policy is enforced before provider execution. A budget breach fails the operation instead of silently falling through to a cheaper or fake result. Actual release, prompt, provider, model, token, latency, and cost metadata are stored on the AI run and exposed through logs/metrics.

Promotion is scoped by operation. Full activation supersedes that operation's prior active release; rollback is performed by promoting a known prior release.

## 4. Delivery protocol

The Integrator sends:

```text
POST <site_connection.delivery_url>
Content-Type: application/json
Idempotency-Key: <package_id>:<package_version>
X-Integrator-Instance-Id: <integrator UUID>
X-Signing-Key-Id: <active key identifier>
X-Timestamp: <UTC timestamp>
X-Signature: <hex HMAC-SHA256>
```

The signature covers the request timestamp and exact request body using the connection secret. The receiver selects a secret by `X-Signing-Key-Id`, checks the configured clock-skew window, verifies the signature in constant time, validates the schema, and persists the immutable version transactionally.

A successful non-empty response must validate as `IncomingPackageReceipt` and match the transmitted `package_id` and `package_version`. Malformed or inconsistent acknowledgements are delivery failures. Empty successful responses remain accepted for compatibility with older Site receivers.

## 5. Key rotation

Each connection has one active key and, during a rotation window, one previous key. Rotation is coordinated as follows:

1. Install the new active key on the Site with the old active key retained as previous.
2. Install the same key identifier and secret on the Integrator connection.
3. Confirm deliveries signed by the new active key.
4. Retire the previous key on both sides.

Unknown and retired key identifiers are rejected. Secrets are write-only API inputs: responses, audit details, logs, and metrics expose identifiers only.

Integrator admin endpoints:

```text
PUT    /api/v1/admin/integration/connections/{id}/signing-key
DELETE /api/v1/admin/integration/connections/{id}/previous-signing-key
```

The Site provides corresponding secured endpoints under `/api/v1/admin/integrator-connections/{id}`.

## 6. Retry, attempt budget, and dead letters

Delivery retries are bounded by durable `attempt_budget_used`. The worker applies exponential outer backoff from `DELIVERY_RETRY_BACKOFF_SECONDS`; provider-level `Retry-After` handling remains inside an individual delivery call. Worker restarts do not reset the budget.

After `DELIVERY_MAX_ATTEMPTS`, the delivery becomes `dead_lettered` with its terminal timestamp and sanitized last error. The outbox event is terminal when all selected targets are delivered or terminally dead-lettered.

Operators can inspect and retry dead letters:

```text
GET  /api/v1/admin/integration/deliveries/dead-letters
POST /api/v1/admin/integration/deliveries/{delivery_id}/retry
```

Manual retry resets the attempt budget, creates a new targeted outbox event, increments `manual_retry_count`, and appends an integration audit event.

## 7. Replay and backfill

Replay re-emits existing immutable package versions; it never creates or mutates canonical packages. Requests must target a connection and be bounded by package identity or time. Optional minimum and maximum versions narrow the selection.

```text
POST /api/v1/admin/integration/replays
Idempotency-Key: <operator request identity>

GET /api/v1/admin/integration/replays/{replay_request_id}
```

The request idempotency key makes scheduling safe to repeat. Each replay has durable scheduled, completed, and failed counts. Delivery targets only the selected connection. On the wire, the original package idempotency key is retained, so the receiver safely acknowledges versions it already stores while accepting versions it missed.

## 8. Correction, retraction, and deletion API

```text
POST /api/v1/admin/integration/packages/{package_id}/revisions
```

The body supplies `operation`, `reason`, and replacement `content` for a correction. The API locks onto the latest stored version, inserts the next immutable version, emits the existing package outbox event, and writes a durable audit event. Delivery then follows the same signed path as ordinary packages.

## 9. Authorization and rate limits

Integration operations use the existing admin token/session authentication boundary.

- Package revisions require `articles:write`.
- Replay, DLQ retry, and key rotation require `jobs:manage`.
- Mutating integration operations share a bounded per-actor rate limiter.

Every sensitive mutation writes an `IntegrationAuditEvent` containing actor, action, resource, timestamp, and non-secret details. The Site's existing request audit middleware covers its key-management endpoints.

## 10. Observability

Structured logs carry package/version, connection, replay request, operation, route/release/model, key identifier, and sanitized failure context where applicable.

Metrics cover:

- package revisions by operation
- media and geography export counts
- AI route/release/model choice and budget rejection
- delivery outcomes, retries, pending work, and dead letters
- replay scheduling and completion/failure
- manual retries
- signing-key rotation/retirement

Secrets and complete signed payloads must not be placed in logs or metric labels.

## 11. Deployment and migration

Integrator migration head: `a6c1e9f42b30`.

Site migration head: `c7e2f6a91d40`.

The migrations preserve existing package rows, delivery rows, and connection secrets. Existing connection secrets become the `legacy` active key. New JSON metadata columns receive empty-array defaults, and delivery counters start at zero.

The integration migration test supports both upgrade-from-previous-head and clean-install paths against an ephemeral PostgreSQL database when `POSTGRES_TEST_URL` is configured. SQLite tests cover API and full sender/receiver behavior without external services.

## 12. Compatibility and deferred scope

Compatibility guarantees:

- `1.1` is additive to `1.0`.
- The receiver accepts both exact versions.
- Legacy taxonomy/region fields remain populated.
- Empty 2xx acknowledgements remain supported.
- Existing single-secret connections migrate to active key ID `legacy`.
- Existing provider environment configuration remains usable only when no quality policy exists.

Connection-level content filtering is intentionally deferred. Every ordinary package still targets every active Site connection unless a replay or manual retry explicitly supplies connection IDs. Adding filtering later requires a separate filter contract, deterministic matching semantics, and upgrade-safe defaults; it is not required for safe correction, replay, delivery, key rotation, metadata, or quality routing.

## 13. Implementation status

- **Implemented:** additive 1.1 contract, lifecycle revisions, replay/status, bounded delivery and DLQ retry, acknowledgement validation, overlapping HMAC keys, typed media/geography/taxonomy, source and AI provenance, runtime quality routing, migrations, audit, metrics, and sender/receiver integration tests.
- **Partial:** none of the required hardening workflows are partial.
- **Stub:** none of the required hardening workflows are stubs.
- **Not implemented:** optional connection-level language/region/category/topic filtering, deferred for the compatibility reasons above; media storage/transcoding/CDN remains intentionally outside the Integrator boundary.
