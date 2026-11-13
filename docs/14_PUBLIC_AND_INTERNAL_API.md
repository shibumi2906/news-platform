# Публичные и внутренние API

**Статус:** Draft 0.1

## 1. Общие правила

HTTPS, `/api/v1`, JSON UTF-8, snake_case, UUID, UTC ISO 8601, OpenAPI 3.1. Ошибка: `{error:{code,message,details,correlation_id}}`. List endpoints используют cursor pagination. Breaking change требует major version; additive change — minor schema version.

## 2. Аутентификация

Admin: session/OIDC + RBAC/CSRF policy. Integrator→Site: connection credential, request signature, timestamp, nonce и idempotency key; механизм окончательно фиксируется ADR. Public API read-only с rate limit. Payment webhook проверяется provider signature.

## 3. Основные endpoints

- Integrator Admin: `/sources`, `/source-runs`, `/events`, `/packages`, `/connections`, `/deliveries`, `/ai-policies`, `/parsers`, `/jobs`, `/reviews`.
- Site ingestion: `POST /incoming-news-packages`, `GET /incoming-news-packages/{id}`, test/health handshake.
- Site editorial: `/articles`, `/article-versions`, `/reviews`, `/publications`, `/schedules`, `/media`, `/channels`.
- Public: `/articles`, `/articles/{id-or-slug}`, `/events`, `/entities`, `/taxonomies`, `/search`, `/languages`.
- Commercial: admin billing/advertising endpoints и `/webhooks/payments/{provider}`.

## 4. News package envelope

Обязательные поля: `schema_version`, `package_id`, `package_version`, `instance_id`, `event_id`, `event_stage`, `content`, `facts`, `entities`, `taxonomy`, `sources`, `language_versions`, `media`, `rights`, `confidence`, `warnings`, `created_at`, `updated_at`. Schema публикуется как отдельный JSON Schema artifact. Неизвестная major version — `422 unsupported_schema_version`.

## 5. Идемпотентность

Повтор с тем же key и тем же body возвращает сохранённый результат; тот же key с другим body — `409 idempotency_conflict`. Nonce/replay window не заменяют idempotency. Async операции возвращают `202` и job URL.

## 6. События

Событие имеет `event_id`, `event_type`, `schema_version`, `occurred_at`, `producer_instance_id`, `aggregate_type/id/version`, `correlation_id`, `causation_id`, `payload`. Payload схемы версионированы. Outbox публикуется at-least-once; consumer идемпотентен.

## 7. Тесты и приёмка

Schema/contract tests, auth/RBAC negatives, replay, idempotency, pagination, large payload, unsupported version, timeout и backward compatibility. Генерируемые clients проходят CI; документация содержит примеры без секретов.

## 8. Реализованный Integrator contract 1.1

`CanonicalNewsPackageEnvelope` 1.1 является additive расширением 1.0. Он добавляет `operation`, `revision_reason`, typed topics/categories/geographies/media, расширенный source provenance и `ai_provenance`. Site принимает только точные версии 1.0 и 1.1 и хранит каждую версию immutable.

Control-plane endpoints находятся под `/api/v1/admin/integration`: package revisions, bounded/idempotent replay with status, dead-letter listing/manual retry и signing-key rotation. Integrator→Site запрос включает `Idempotency-Key`, `X-Integrator-Instance-Id`, `X-Signing-Key-Id`, `X-Timestamp` и `X-Signature`. Полная wire/runbook спецификация находится в `NEWS_INTEGRATOR_INTERFACE.md`.

## Downstream sites that request materials

In **Admin → Selected materials → Connected sites**, set the delivery mode of
an existing registered connection to **Site requests materials**. Connections
use the existing ID and HMAC key provisioning. Keep the shared key on the
downstream server. The push worker skips connections in pull mode.

Send a server-to-server `POST /integrator-api/api/v1/site-feed/materials` with
`Content-Type: application/json`. Example body: `{"topic":"texas-news","limit":50}`.
Use the topic slug configured in the integrator. The response contains canonical
package versions in ascending order and a `cursor` to send back verbatim with
the same topic. Persist each topic cursor after processing the page. Repeat
while `has_more` is true and poll periodically for new versions. Handle
correction and withdrawal operations, and deduplicate by package ID and version.
Start with an empty cursor to replay a topic. The Connected sites view shows the
time of the latest successful request.

Send `X-Connection-Id`, `X-Signing-Key-Id`, `X-Timestamp` (UTC ISO 8601),
`X-Nonce` (a fresh UUID per request) and `X-Signature`. Compute the signature
using HMAC-SHA256 with the connection secret and the exact bytes
`timestamp + "\n" + nonce + "\nsite-feed/materials\n" + body`. Use the lowercase
hex digest. Requests outside the five-minute window and reused nonces are rejected.
A reverse proxy needs to route this endpoint to the integrator API. The bundled
Caddy config contains the route.

For YouTube channel and playlist sources, set `YOUTUBE_API_KEY` in the deploy
environment. **Check source** shows titles and descriptions from public videos.
