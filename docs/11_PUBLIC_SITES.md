# Публичные сайты

**Статус:** Draft 0.1

## 1. Основа

Один Next.js-шаблон поддерживает несколько дизайн-тем без изменения API и модели контента. Конкретная установка настраивает бренд, навигацию, домен, языки, категории, главную и рекламные placements.

## 2. Страницы

Главная/лента, категория/тема/регион, статья, событие/хронология, персона, компания, проект/произведение, поиск, языковая версия и юридические/редакционные страницы. Состояния loading/empty/error/404/410 обязательны.

## 3. Требования

SSR/SSG/ISR выбираются по типу страницы; публичный web читает только Site API/read model. Responsive, keyboard navigation, WCAG 2.2 AA как целевой уровень, LTR/RTL, Core Web Vitals budget, image optimization, безопасный HTML и consent-aware analytics.

## 4. Темы

Design tokens, компоненты и page slots стабильны; пользовательская тема не правит доменные компоненты. Theme manifest имеет version и compatibility range. Обновление не перезаписывает кастомизацию.

## 5. Приёмка

Тесты на все типы страниц, языки/RTL, mobile/desktop, accessibility, structured data, cache invalidation, preview unpublished content и отсутствие admin data в public bundle.

