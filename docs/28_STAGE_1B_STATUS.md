# Статус Stage 1B — RSS → Site ingestion

**Статус:** implemented vertical slice; последующие этапы не начаты.

## Реализованный поток

1. `source-worker` опрашивает активный RSS/Atom `source`, передавая сохранённые
   ETag/Last-Modified и сохраняя новые checkpoint values.
2. Новый материал сохраняется вместе с временным 1:1 событием и outbox event.
3. `processing-worker` создаёт canonical package версии 1 и delivery event.
4. `delivery-worker` подписывает payload HMAC v1, ведёт attempts и повторяет
   недоставленные отправки.
5. `site-api` проверяет connection, timestamp, nonce, HMAC, версию подписи и
   schema major; затем идемпотентно сохраняет immutable incoming package version.

Compose запускает migration jobs перед API и workers. Для demo-потока оператор
создаёт RSS source и согласованную пару connection с одинаковым UUID и secret.

## Явные границы

Не входят в Stage 1B: Admin API/UI, автоматический provisioning connections,
HTML/API/browser connectors, AI, event clustering, translations, editorial
workflow, public site, media, dashboard, payments и advertising.
