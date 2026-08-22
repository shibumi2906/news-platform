# Тестирование и приёмка

**Статус:** Draft 0.1

## 1. Уровни

Unit; schema/contract; component с реальными PostgreSQL/Redis; integration с mock providers; end-to-end; migration; security; performance; accessibility/visual; backup/restore; installation/update/rollback.

## 2. Обязательные сквозные сценарии

Источник→нормализация→AI→event→package→доставка→редакция→публикация; update без перезаписи; технический/смысловой дубль и новая стадия; 16 языков/RTL; media rights withdrawal; channel failure; payment webhook duplicate; site dashboard outage; backup restore; один интегратор→несколько сайтов и несколько интеграторов→один сайт.

## 3. Test assets

Версионированные fixtures HTML/API/packages, frozen AI eval sets, factories, deterministic clocks/UUID, provider mocks и demo configuration. Production secrets/data запрещены. Contract fixtures являются общими для двух шаблонов.

## 4. Gates

PR: lint/type/unit/schema/security fast checks. Main: integration/contract/migration. Release candidate: E2E, installation, restore, rollback, performance baseline, accessibility и security suite. Flaky test не игнорируется молча; имеет owner и срок.

## 5. Приёмка

Requirement traceability matrix связывает MUST→test→result. Критические тесты проходят полностью; отсутствуют открытые critical/high security defects; schema compatibility, restore и clean install доказаны отчётами.

