# Надёжность, наблюдаемость и резервное копирование

**Статус:** Draft 0.1

## 1. Надёжность

Timeout, bounded retry with jitter, circuit breaker, idempotency, transactional outbox, DLQ и manual replay. Graceful shutdown не подтверждает незавершённую задачу. Redis не является единственным хранилищем принятого события.

## 2. Наблюдаемость

Structured logs, metrics, traces и correlation/causation IDs. Golden signals для API; queue depth/age; source freshness; parser failure; AI latency/cost/schema failure; delivery lag; publication errors; dashboard lag; billing webhook errors. Интегратор наблюдается только локально.

## 3. Backup/restore

Отдельно для каждой установки: PostgreSQL, object storage, manifest/version, безопасная configuration и пользовательские adapters/themes. Backup шифруется, имеет checksum и retention. Restore сначала выполняется в staging namespace и проходит smoke test.

## 4. SLO

Численные SLO/RPO/RTO назначаются после объёмов и фиксируются в `22_OPEN_DECISIONS.md`; отсутствие чисел не отменяет автоматический restore drill, alerts и capacity monitoring.

## 5. Приёмка

Проверяются provider/site/Supabase/Redis/S3 outage, worker crash, duplicate delivery, DLQ replay, log redaction, alert routing и восстановление чистой установки из backup.

