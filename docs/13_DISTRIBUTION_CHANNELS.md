# Каналы распространения

**Статус:** Draft 0.1

## 1. Архитектура

Адаптер получает immutable publication version и channel policy, создаёт channel-specific draft, валидирует его и публикует после установленного approval. Поддерживаемые классы: Telegram, социальные сети, CMS, email, partner API и мобильные push; конкретный адаптер включается отдельно.

## 2. Контракт

Вход: publication/version, locale, media refs, target account, template revision. Выход: external ID/URL, status, published_at и diagnostics. Уникальность `(channel, account, publication_version)` предотвращает дубли.

## 3. Правила

Credentials scoped и шифруются. Rate limits и provider errors обрабатываются независимо. Изменение статьи не редактирует внешний пост автоматически без policy. Delete/update требуют явного действия и audit. UTM/attribution настраиваются.

## 4. Тесты и приёмка

Sandbox/mocks, формат/лимиты, auth expiry, 429/5xx, duplicate callback, partial media failure, retry и manual reconciliation. Ошибка канала не снимает публикацию сайта.

