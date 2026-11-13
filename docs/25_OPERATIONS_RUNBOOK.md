# Руководство по эксплуатации

**Статус:** Draft 0.1

## 1. Ежедневные проверки

Health/readiness, queue age/DLQ, source freshness, parser errors, AI error/cost, delivery/publication lag, disk/DB growth, backup age, certificate expiry; на сайте — dashboard lag, payment/channel webhook status.

## 2. Инциденты

Для каждого: symptom→impact→safe diagnostics→containment→recovery→verification→escalation→postmortem. Сценарии: API down, DB unavailable, Redis loss, S3 unavailable, source blocked, parser drift, AI outage/budget exhaustion, delivery/auth failure, Supabase outage, stuck publication, payment webhook backlog, disk full и certificate failure.

## 3. Безопасные операции

DLQ retry выполняется после устранения причины и preview scope; credential rotation поддерживает overlap; backup restore — только в staging до проверки; migration запускается один раз; очистка cache не удаляет authoritative data. Все команды имеют dry-run где возможен риск.

## 4. Коммуникация и аудит

Фиксируются incident ID, UTC timeline, affected instances, correlation IDs, действия и результат. Секреты/personal data не вставляются в ticket. Postmortem обязателен для data loss, security и длительного SLO breach.

## 5. Приёмка

Quarterly restore и credential rotation drills; runbook test для ключевых отказов; команды соответствуют Windows/Linux scripts и актуальной версии.

## 6. Integrator delivery recovery

1. Inspect `/api/v1/admin/integration/deliveries/dead-letters` and confirm the affected connection/package scope.
2. Correct the remote availability, acknowledgement, schema, signature, or key-ID cause.
3. Retry only the selected delivery with `POST /api/v1/admin/integration/deliveries/{id}/retry`.
4. Confirm the attempt budget, delivery outcome metric, Site immutable version, and integration audit event.

For missed ranges, schedule an idempotent replay with a package or time bound and poll `/api/v1/admin/integration/replays/{id}` until completed or failed counts settle. Replay never mutates canonical packages.

Key rotation uses an overlap window: install the new active/old previous pair on Site, rotate Integrator, verify new-key traffic, then retire previous keys on both sides. Use key identifiers in diagnostics; never copy secrets into logs or tickets.
