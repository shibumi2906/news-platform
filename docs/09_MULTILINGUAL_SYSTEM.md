# Многоязычная система

**Статус:** Draft 0.1

## 1. Модель

Языки берутся из глоссария. Канонический контент имеет source language; `language_version` привязан к object, object version, locale и translation version. Интегратор создаёт переводы; сайт получает их и может редакционно изменить только свою article version.

## 2. Перевод

Сохраняются исходник, provider/model, prompt, terminology revision, quality flags и reviewer. Кэш-ключ: `(content_hash, target_locale, terminology_revision, prompt_version)`. Имена, названия произведений, даты, единицы, цитаты и URL проходят отдельные проверки. Back-translation не считается доказательством качества.

## 3. Интерфейс и SEO

Locale влияет на routing, format и fallback, но не на UUID. Арабский поддерживает RTL; смешанный bidi-текст тестируется. `hreflang`, canonical и sitemap формируются только для опубликованных версий. Отсутствующий перевод не создаёт пустую индексируемую страницу.

## 4. Контроль качества

Glossary/translation memory имеют версии и область применения. Автоматическая публикация языка разрешается только после eval. Проверяются полнота, числа, имена, запрещённые добавления, HTML preservation, длина meta fields и font coverage.

## 5. Приёмка

Все 16 языков проходят rendering fixtures; переключение не меняет материал; исправление перевода создаёт версию; изменение исходника не перезаписывает утверждённый текст сайта.

