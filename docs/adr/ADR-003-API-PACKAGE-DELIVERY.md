# ADR-003: Доставка пакетов через API

**Статус:** Accepted

## Решение

Integrator доставляет immutable versioned packages в Site Ingestion API по TLS с authentication/signature, idempotency, retry и DLQ.

## Последствия

Нет cross-DB access; schema compatibility и contract tests обязательны; точный механизм подписи остаётся OD-04.

