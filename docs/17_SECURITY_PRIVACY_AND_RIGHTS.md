# Безопасность, приватность и права

**Статус:** Draft 0.1

## 1. Модель угроз

Недоверенные: HTML/JSON/media источников, AI output, parser code, webhooks и межсистемный traffic. Учитываются SSRF, prompt injection, XSS, SQL injection, replay, credential theft, supply-chain, sandbox escape, privilege escalation и content-rights violation.

## 2. Контроли

TLS; least privilege; RBAC; MFA-ready admin; encrypted/scoped/rotatable secrets; CSRF/CORS/trusted hosts; rate limits; input/output schemas; HTML sanitization; egress policy; non-root/read-only containers; dependency/image scanning; audit and alerting.

## 3. Данные и приватность

Data classification: public, internal, confidential, secret, personal, financial. Для каждого класса задаются storage, access, retention и export. Логи не содержат secrets/full payment data. DSAR/deletion применяются к персональным данным, но не уничтожают обязательный финансовый/audit след.

## 4. Контент и медиа

Хранятся provenance, author, license, territory, expiration, attribution и allowed uses. Rights change вызывает поиск зависимых публикаций и редакционное действие. AI-media маркируется и не выдаётся за документальное изображение.

## 5. Приёмка

Threat model review, SAST/dependency/container scan, auth/RBAC/replay/SSRF/XSS tests, parser sandbox tests, secret scan, backup encryption restore test и rights withdrawal drill.

