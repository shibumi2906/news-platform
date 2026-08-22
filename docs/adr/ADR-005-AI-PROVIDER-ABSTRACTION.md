# ADR-005: Абстракция AI-провайдеров

**Статус:** Accepted

## Решение

Доменные операции используют provider-neutral AI Gateway, строгие schemas, versioned prompts и configurable routing.

## Последствия

Модель заменяема; provider-specific payload остаётся в adapter; eval и cost/latency telemetry обязательны.

