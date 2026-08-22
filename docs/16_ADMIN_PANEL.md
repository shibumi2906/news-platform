# Административные панели

**Статус:** Draft 0.1

## 1. Разделение

У каждой установки собственная панель. Integrator Admin: источники, parser lab, события, пакеты, AI, языки, connections, deliveries, costs, jobs и локальная наблюдаемость. Site Admin: inbox, редакция, публикации, SEO, media, channels, analytics export, users, billing, advertising и configuration.

## 2. Общие требования

API-first, RBAC, MFA-ready, audit, optimistic locking, server-side secrets, pagination/filtering, bulk actions с preview, доступные error/retry состояния, UTC+configured timezone. Опасные действия требуют confirmation и reason; credentials после сохранения не показываются.

## 3. Операционные экраны

Очереди/DLQ, job details с correlation ID, health, version/migrations, test connection, import/export безопасной конфигурации и diff обновления. Панель не подключается напрямую к БД.

## 4. Приёмка

Role matrix и negative tests для каждого раздела; keyboard/RTL/responsive; secret masking; audit критических действий; большие списки не загружаются целиком.

