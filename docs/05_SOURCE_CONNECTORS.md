# Коннекторы источников

**Статус:** Draft 0.1

## 1. Назначение

Единый интерфейс `discover → fetch → normalize → checkpoint` для RSS/Atom, официальных API, YouTube, HTML, Playwright, опционального Selenium и Gemini Search grounding.

## 2. Контракт адаптера

Вход: `source_id`, config revision, cursor/checkpoint, time window, limits. Выход: список `SourceCandidate` с URL, external ID, title, body/excerpt, author, published/updated time, language, media refs, raw provenance и fetch metadata. Адаптер не создаёт событие и не пишет статью.

## 3. Политики

Учитываются robots.txt, ToS, rate limits, лицензия и допустимый способ хранения. Secrets не входят в config export. HTTP использует timeout, conditional requests, retry-after и bounded retry. Browser применяется только при невозможности получить данные более дешёвым способом.

## 4. Типы

- RSS/API/YouTube: стабильный external ID и incremental cursor.
- HTML: selector config или одобренный parser adapter.
- Browser: изолированный context, запрет произвольных downloads и внутренних сетей.
- Search: обнаруживает ссылки и утверждения, но результат поиска сам по себе не считается первоисточником.

## 5. Ошибки и контроль

Различаются temporary, auth, rate-limit, schema drift, blocked и permanent. Source health учитывает freshness, success rate и количество извлечённых полей. После порога ошибок источник получает `degraded/paused`, но история не удаляется.

## 6. Тесты и приёмка

Fixtures без сети для каждого адаптера; cursor/idempotency; timezone; malformed data; 429/5xx; auth rotation; пустая страница; изменение DOM. Новый источник активируется только после preview и подтверждения администратора.

