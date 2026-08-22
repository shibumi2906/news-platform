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

