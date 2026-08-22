# Создание и восстановление парсеров

**Статус:** Draft 0.1

## 1. Поток

Администратор передаёт URL, HTML/DOM snapshot либо HTML-код. Система предлагает selector config; код генерируется только когда декларативного парсера недостаточно. Версия проходит lint, dependency allowlist, static security scan, sandbox execution, fixture tests и preview полей. Активация — только вручную.

## 2. Изоляция

Parser runner не имеет Docker socket, production credentials, DB access и доступа к internal/cloud metadata networks. Ограничиваются CPU, RAM, время, output, filesystem и domains. Генерируемый код не выполняется в API или основном worker.

## 3. Версии и repair

Хранятся input snapshot, generated artifact, model/prompt version, test report, reviewer и activation history. При schema drift активная версия не перезаписывается: создаётся candidate repair, сравнивается с предыдущими fixtures и после approval заменяет active version. Быстрый rollback обязателен.

## 4. Выходной контракт

Parser возвращает только нормализованный candidate и diagnostics; произвольные side effects запрещены. Невалидные поля отклоняются JSON Schema.

## 5. Тесты и приёмка

Fixtures минимум: обычная статья, список, отсутствующее поле, изменённый DOM, вредоносный HTML, timeout и redirect. Escape/SSRF tests обязательны. Парсер считается готовым при воспроизводимом результате, заполнении обязательных полей и отсутствии регрессии на утверждённых fixtures.

