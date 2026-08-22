# Установка, развёртывание и обновления

**Статус:** Draft 0.1

## 1. Артефакты

Versioned images, Dockerfiles, production/development Compose, `.env.example`, migrations, `install/start/stop/restart/update/backup/restore/status/logs` для Windows/Linux, setup wizard и checksums/SBOM.

## 2. Install

Preflight Docker/Compose, architecture, ports, disk/RAM, writable volumes и network. Генерируется instance config; запускаются infrastructure, migration job и setup service. Wizard создаёт первого admin/instance ID, домен, locale/timezone, storage и backup; затем product-specific settings и self-test. Bootstrap закрывается.

## 3. Update/rollback

Compatibility check→backup→verified images→preflight→single migration job→rolling service update→health/smoke→version record. Пользовательские themes/sources/connections/secrets не перезаписываются. Необратимая migration требует предупреждения и restore plan.

## 4. Profiles

Single-server Compose и scalable external DB/Redis/S3 используют тот же application code/contracts. Kubernetes/Helm — только после отдельного решения.

## 5. Приёмка

Чистые Windows/Linux install, повторный install, remote integrator-site connection, domain/TLS, update from previous supported version, failed migration rollback, backup restore и сохранение custom configuration.

