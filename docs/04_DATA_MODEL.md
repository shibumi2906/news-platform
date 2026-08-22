# Модель данных

**Статус:** Draft 0.1  
**Зависимости:** `01_PRODUCT_REQUIREMENTS.md`, `02_SYSTEM_ARCHITECTURE.md`

## 1. Правила

Интегратор и сайт имеют отдельные PostgreSQL БД. Все внешние ID — UUID; время — UTC; изменяемые сущности имеют `created_at`, `updated_at`, `version`; удаление бизнес-данных по умолчанию логическое. JSONB разрешён для provider payload и расширяемых атрибутов, но не вместо ключевых связей.

## 2. Общие сущности установки

`instance`, `user`, `role`, `permission`, `user_role`, `api_credential`, `configuration_revision`, `audit_log`, `outbox_event`, `job`, `job_attempt`, `dead_letter`, `media_asset`, `media_rights`, `prompt_template`, `ai_operation_run`.

Обязательные ограничения: уникальный `instance_id`; email пользователя уникален внутри установки; секрет хранится только как hash/encrypted value; outbox содержит уникальный `event_id`; audit log append-only.

## 3. Интегратор

- Источники: `source`, `source_endpoint`, `source_credential`, `source_schedule`, `source_run`, `parser_adapter`, `parser_version`, `source_snapshot`.
- Контент: `source_material`, `material_fact`, `entity`, `material_entity`, `event`, `event_stage`, `event_material`, `event_relation`.
- AI и языки: `ai_policy`, `ai_result`, `terminology_entry`, `language_version`, `quality_review`.
- Пакеты: `canonical_news_package`, `package_version`, `package_source`, `package_media`.
- Доставка: `site_connection`, `connection_filter`, `delivery`, `delivery_attempt`.

Ключи уникальности: `(source_id, external_id)` либо `(source_id, canonical_url_hash)`; `(package_id, package_version)`; `(connection_id, idempotency_key)`; `(object_type, object_id, language_code, source_version)`.

## 4. Сайт

- Приём: `integrator_connection`, `incoming_package`, `incoming_package_version`, `ingestion_attempt`.
- Редакция: `site_article`, `article_version`, `article_source_link`, `editorial_task`, `review_decision`, `correction_notice`.
- Публикация: `publication`, `publication_schedule`, `slug`, `redirect`, `taxonomy_term`, `article_taxonomy`, `public_entity`, `article_entity`.
- Каналы: `distribution_channel`, `distribution_job`, `external_publication`.
- Аналитика: `site_event`, `analytics_hourly`, `analytics_daily`, `dashboard_outbox`.
- Коммерция: `customer`, `plan`, `subscription`, `invoice`, `payment`, `refund`, `ledger_entry`, `advertiser`, `placement`, `campaign`, `creative`, `ad_delivery_aggregate`.

`incoming_package_version.payload` неизменяем. `article_version` содержит snapshot редакционного текста. `publication.active_article_version_id` переключается атомарно. `(connection_id, idempotency_key)` уникален.

## 5. Жизненные циклы

Статусы реализуются enum/check constraints и переходами сервисного слоя. Запрещены переходы `published → draft` без новой версии, повторное списание одного provider event и физическое удаление сущностей с финансовым/audit следом.

## 6. Индексы и retention

Индексируются внешние ID, статусы очередей, расписания, `event_id`, `published_at`, slug+language, source URL hash и foreign keys. Большие журналы и попытки партиционируются по времени после подтверждения нагрузки. Retention назначается по классу данных; финансовый и audit след не очищается общим job.

## 7. Миграции и тесты

Alembic-миграции forward/backward там, где безопасно; breaking migration имеет backup и отдельный rollback. Обязательны tests constraints, cascade/restrict, idempotency, конкурентной публикации, immutable payload, миграции с предыдущей поддерживаемой версии.

## 8. Критерии приёмки

Для каждой сущности определены владелец, PK/FK, обязательность, уникальность, статус и политика удаления; схема не требует cross-database join; OpenAPI/JSON Schema поля трассируются к модели.

