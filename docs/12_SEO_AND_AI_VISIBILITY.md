# SEO и видимость для AI-систем

**Статус:** Draft 0.1

## 1. Индексация

Стабильные URL и slug history; canonical; `hreflang`; robots; XML/news/image sitemap; RSS; корректные 301/404/410; noindex для preview, staging, фильтров без ценности и неопубликованных языков.

## 2. Метаданные

Title/description, Open Graph, dates, author/editorial organization, provenance links и Schema.org (`NewsArticle`, `Person`, `Organization`, `Movie`/подходящий тип, `BreadcrumbList`). Structured data строится из тех же полей, что видит человек.

## 3. Машиночитаемость

Публичный read-only API, RSS и семантические entity pages. Доступ AI crawlers управляется явной policy; обещания цитирования или позиции запрещены. Лицензия и ограничения повторного использования указываются где применимо.

## 4. Контроль

Публикация/изменение/снятие инвалидирует cache и обновляет sitemap. CI проверяет broken links, duplicate canonical, schema validation, missing hreflang reciprocity и accidental indexing.

## 5. Приёмка

Каждая опубликованная версия имеет один canonical, валидные metadata/schema и доступна без выполнения клиентского JS в существенной части; staging не индексируется.

