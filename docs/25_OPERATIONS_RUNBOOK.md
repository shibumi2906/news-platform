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

