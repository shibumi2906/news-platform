# Интеграция с дашбордом

**Статус:** Draft 0.1  
**Утверждённое правило:** данные отправляет только сайт.

## 1. Граница

Интегратор не имеет Supabase URL/key и не отправляет туда события или агрегаты. Сайт экспортирует только согласованные метрики через server-side HTTP. Дашборд не управляет сайтом и не является operational store.

## 2. Наборы данных

Site health/latency; traffic aggregates; популярность материалов/тем/языков/сущностей; received/accepted/rejected/published package counts; time-to-publication; ingestion/publication errors; active language count; согласованные обезличенные billing/advertising aggregates.

## 3. Доставка

Операция сайта пишет `dashboard_outbox` в той же транзакции. Exporter отправляет срочные events и hourly/daily aggregates с schema version, site instance ID, period, metric, dimensions и value. Повторы с idempotency key; backoff; DLQ; reconciliation по диапазону времени.

## 4. Приватность и отказоустойчивость

Не передаются текст статьи, credentials, PII, платёжные реквизиты и raw visitor events. Недоступность Supabase не блокирует ingestion или publication. Retention outbox и lag alert задаются конфигурацией.

## 5. Приёмка

Network/config test подтверждает отсутствие Supabase у интегратора; duplicate export не удваивает метрику; outage/recovery и reconciliation проверены; dashboard schema отделена от основной БД сайта.

