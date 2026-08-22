# ADR-002: Модульный monorepo

**Статус:** Accepted

## Решение

Два продуктовых шаблона, frontends, workers, schemas и tests находятся в одном monorepo с явными domain boundaries и отдельными migrations.

## Последствия

Contract changes атомарно проверяются CI; запрещены общие DB models и неявные импорты между site/integrator domain.

