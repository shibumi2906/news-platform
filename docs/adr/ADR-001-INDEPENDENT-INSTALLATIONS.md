# ADR-001: Независимые установки

**Статус:** Accepted

## Решение

Интегратор и сайт поставляются как тиражируемые шаблоны. Каждый экземпляр имеет отдельные БД, credentials, configuration, admin и lifecycle. Общая operational DB и обязательный central registry запрещены.

## Последствия

Связь только через versioned API; backup/update/security blast radius изолированы; общие изменения требуют совместимых contracts.

