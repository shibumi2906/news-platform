# AI-конвейер обработки

**Статус:** Draft 0.1

## 1. Операции

Определение языка и релевантности, классификация, извлечение фактов/сущностей, summary, оценка конфликта, важность, дедупликация-кандидат, редакционная карточка, перевод и при необходимости media brief. Каждая операция мала, версионирована и имеет строгую схему.

## 2. Выполнение

`validated input → prompt render → provider/model route → structured output → schema validation → deterministic checks → confidence policy → accept/retry/fallback/review`. Сохраняются operation ID, prompt version, model, provider, latency, tokens, cost, input hash и результат. Sensitive/raw content передаётся только разрешённым провайдерам.

## 3. Маршрутизация

Политика задаёт primary/fallback, budget, timeout, max attempts и пороги. Повтор с той же моделью допускается только для исправимой ошибки формата. Низкая уверенность не маскируется повтором; применяется мощная модель или человек.

## 4. Промпты и eval

Промпты — данные, а не строки в коде. Изменение создаёт новую версию и прогоняется по замороженному eval-набору: точность фактов, schema validity, unsupported claims, классификация, качество перевода, стоимость и latency. Автоматический rollout имеет canary и rollback.

## 5. Безопасность

Источник считается недоверенным и не может изменять системную инструкцию. Tool use по умолчанию запрещён. PII/secrets редактируются по policy. Output не публикуется напрямую без детерминированных и редакционных правил.

## 6. Приёмка

Все операции имеют Pydantic/JSON Schema, fixture/eval tests, budget и failure route; воспроизводимо определяется версия результата; provider outage не теряет исходный материал.

