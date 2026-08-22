# Платежи и биллинг

**Статус:** Draft 0.1

## 1. Граница

Модуль принадлежит сайту. Provider gateway изолирован adapter interface. Billing владеет customer, plan/product, subscription, invoice, payment, refund и double-entry-like immutable ledger/audit; сайт не хранит card data.

## 2. Потоки

Checkout создаётся server-side; provider webhook является авторитетным подтверждением после проверки подписи. Каждый provider event и idempotency key уникален. Out-of-order события сверяются по provider object/version/time и reconciliation job. Refund/chargeback не правит старую запись, а создаёт компенсирующую.

## 3. Деньги и доступ

Amount — integer minor units + ISO currency. Налоги/чеки/страны — provider/policy adapters после решения. Entitlement меняется только после устойчивого billing state и может быть восстановлен reconciliation.

## 4. Безопасность и тесты

Scoped secrets, signature/replay protection, PII minimization, restricted finance roles, immutable audit. Contract mocks: success/failure/pending, duplicate/out-of-order webhook, subscription lifecycle, refund, currency, timeout и reconciliation.

## 5. Приёмка

Повтор webhook не удваивает деньги/entitlement; ledger сходится с provider report; секреты и платёжные данные не уходят в дашборд; конкретный provider заменяем без изменения домена.

