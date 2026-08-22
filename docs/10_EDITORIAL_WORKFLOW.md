# Редакционный процесс сайта

**Статус:** Draft 0.1

## 1. Поток

`received → processing → draft/duplicate_candidate/rejected_as_irrelevant → needs_review → approved → scheduled/publishing → published → corrected/unpublished/archived`. Переходы исполняет сервис с RBAC, reason и audit event.

## 2. Приём пакета

Входящий payload сохраняется неизменяемо. Из него создаётся независимый `site_article`. Новая package version показывается как diff фактов, источников, переводов и прав; редактор принимает поля выборочно. Автоматическое молчаливое обновление опубликованного текста запрещено.

## 3. Версии и совместная работа

Каждое сохранение, влияющее на публикацию, создаёт article version. Используется optimistic locking. Approval фиксирует reviewer, version и timestamp. Автор не может единолично утверждать собственный материал, если включён four-eyes mode.

## 4. Публикация

Schedule/embargo исполняются в UTC. Переключение active version и запись publication event атомарны. Correction содержит видимое объяснение по policy; unpublish создаёт redirect/status по SEO policy. Канальные ошибки не меняют статус сайта.

## 5. Приёмка

Проверяются все разрешённые/запрещённые переходы, конкурентное редактирование, diff update, embargo, correction, unpublish, audit и восстановление после сбоя worker.

