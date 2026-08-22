# Справочник конфигурации

**Статус:** Draft 0.1

## 1. Приоритет

Defaults < config file < environment < secret file/manager. Production validation fail-fast. Secrets никогда не возвращаются admin API. Изменения отмечены как runtime reload либо restart required.

## 2. Группы переменных

- Instance: `APP_ENV`, `INSTANCE_ID`, `INSTANCE_TYPE`, `APP_VERSION`, `TIMEZONE`, `PUBLIC_BASE_URL`.
- DB/queue: `DATABASE_URL`, pool/timeouts, `REDIS_URL`, queue names/concurrency.
- Storage: endpoint, region, bucket/prefix, access/secret, signed URL TTL.
- Security: session/signing keys, allowed hosts/origins, cookie policy, replay window, credential encryption key.
- AI: provider endpoints/keys, model policy, token/cost budgets, timeouts, retry and prompt registry revision.
- Sources/browser: schedules, HTTP user agent, rate/concurrency, browser limits/egress.
- Site: languages, theme, search, cache, publication and editorial policies.
- Dashboard (site only): URL/key, batch size, timeouts, outbox retention. Эти переменные запрещены в integrator profile.
- Billing/channels: provider-specific namespaced secrets.
- Operations: log level, OTEL, metrics, backup destination/retention, alert destinations.

## 3. Проверки

`.env.example` содержит безопасные placeholders и комментарии. Config schema типизирована; URL/UUID/enum/ranges проверяются. Startup report показывает источники значений без секретов. Deprecated variable имеет warning и срок удаления.

## 4. Приёмка

Тесты defaults/overrides/missing secrets/invalid values; integrator отклоняет dashboard config; export/import не раскрывает secret; документация генерируется или сверяется со schema в CI.

