# Реклама и монетизация

**Статус:** Draft 0.1

## 1. Модель

`advertiser → campaign → creative → placement/schedule/targeting`. Inventory и placements принадлежат теме сайта; creative имеет media rights, approval, disclosure и locale variants. Прямая продажа вызывает Billing через внутренний интерфейс, но рекламный модуль не проводит платежи.

## 2. Показ

Public web запрашивает eligible creative по placement/context. Персональные чувствительные признаки не используются. Frequency/click tracking и consent зависят от privacy policy. Fail closed: ошибка рекламы не ломает страницу; sponsored content явно маркируется.

## 3. Учёт

Raw high-volume events хранятся локально по retention; сайт отправляет в дашборд только согласованные агрегаты. Budget/pacing и billing reconciliation идемпотентны. Fraud/anomaly flags не удаляют исходный audit.

## 4. Тесты и приёмка

Schedule/timezone, placement compatibility, locale, rights expiry, approval, budget/pacing, duplicate events, disclosure, ad blocker/no-fill и billing failure. Реклама не влияет на редакционный статус и не раскрывает PII.

