# План реализации

**Статус:** Draft 0.1  
**Принцип:** полная версия строится вертикальными проверяемыми инкрементами; этап не означает урезанный MVP.

## 1. Последовательность

1. Repository foundation: tooling, shared contracts, config, logging, auth skeleton, CI, Compose.
2. Integrator core: sources, snapshots, normalization, jobs, storage, admin foundation.
3. AI/event core: prompt registry, gateway, extraction, dedup/event clustering, translations, eval.
4. Package/delivery: schemas, connections, signing, outbox, retry/DLQ, contract tests.
5. Site core: ingestion, immutable packages, editorial versions, publication/read model.
6. Public web: pages, themes, search, multilingual/RTL, SEO/API.
7. Distribution/media: rights, derivatives, channel adapters.
8. Dashboard: site-only outbox/export/reconciliation.
9. Billing/advertising: ledgers, provider adapters, campaigns/placements.
10. Hardening: security, observability, install/update/rollback, restore, capacity and full E2E.

## 2. Правило задачи для Claude Code

Каждая задача указывает: цель; затрагиваемые файлы; требования/не-требования; входные schemas; data migrations; API/events; auth; errors; tests; acceptance commands; documentation update. Сначала inspect, затем plan, затем code; запрещены незаявленные архитектурные решения и массовое переписывание.

## 3. Definition of Done

Код, types, migrations, unit/integration/contract tests, observability, security checks, docs и demo fixture; clean startup; no secrets; requirement traceability; review принят. Stub/TODO не считается реализацией MUST.

## 4. Release milestones

R1 foundation/contracts; R2 integrator pipeline; R3 site editorial/publication; R4 public multilingual portal; R5 distribution/commercial; R6 production hardening/full acceptance. Каждая версия совместима в пределах объявленного contract range.

