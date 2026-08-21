# Каналы распространения

**Статус:** Telegram, Facebook, Instagram, TikTok, X и YouTube implemented;
provider activation requires server-side OAuth credentials and per-channel configuration.

## 1. Архитектура

Адаптер получает immutable publication version и channel policy, создаёт channel-specific draft, валидирует его и публикует после установленного approval. Поддерживаемые классы: Telegram, социальные сети, CMS, email, partner API и мобильные push; конкретный адаптер включается отдельно.

## 2. Контракт

Вход: publication/version, locale, media refs, target account, template revision. Выход: external ID/URL, status, published_at и diagnostics. Уникальность `(channel, account, publication_version)` предотвращает дубли.

## 3. Правила

Credentials scoped и шифруются. Rate limits и provider errors обрабатываются независимо. Изменение статьи не редактирует внешний пост автоматически без policy. Delete/update требуют явного действия и audit. UTM/attribution настраиваются.

До постановки задания выполняется capability check. Facebook поддерживает text/link/image/video; Instagram — image/reel; TikTok и YouTube — video; X — text/link (media upload требует отдельного OAuth scope и не включается без него). Media-провайдеры принимают только публичный HTTPS URL, полученный из `media_url_template` канала; object-store credentials в worker не передаются.

## 4. Тесты и приёмка

Sandbox/mocks, формат/лимиты, auth expiry, 429/5xx, duplicate callback, partial media failure, retry и manual reconciliation. Ошибка канала не снимает публикацию сайта.
