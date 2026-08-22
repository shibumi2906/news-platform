# ADR-006: Фоновые задачи и transactional outbox

**Статус:** Accepted

## Решение

Длительные/внешние операции выполняются workers. Domain event записывается в outbox в одной DB transaction; доставка at-least-once, consumer идемпотентен.

## Последствия

Нужны retry/DLQ/reconciliation и queue monitoring; конкретная queue — OD-01.

