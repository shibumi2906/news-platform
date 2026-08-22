# Открытые решения

**Статус:** Draft 0.1

Решение закрывается ADR: owner, deadline, варианты, рекомендация, последствия и evidence.

| ID | Решение | Рекомендация до ADR | Нужно для |
|---|---|---|---|
| OD-01 | Queue | Celery + Redis | foundation |
| OD-02 | Reverse proxy | Caddy | deployment |
| OD-03 | Object storage default | MinIO self-hosted, S3 cloud | deployment |
| OD-04 | Inter-system signing | HMAC v1 с rotation; оценить asymmetric | delivery |
| OD-05 | Search | PostgreSQL FTS + pgvector; OpenSearch по thresholds | site |
| OD-06 | Site Admin placement | отдельный protected Next.js app | repository |
| OD-07 | AI providers/models | adapter policy после cost/quality eval | AI |
| OD-08 | Analytics source | server logs + выбранный analytics adapter | dashboard |
| OD-09 | Payment providers/countries | после первой страны установки | billing |
| OD-10 | SLO/RPO/RTO/retention | после traffic/source/cost forecast | operations |
| OD-11 | Capacity profiles | benchmark small/medium/large | deployment |
| OD-12 | Kubernetes/Helm | не включать до подтверждённой необходимости | release |
| OD-13 | `pt-BR`, `zh-TW` | pt-BR; zh-TW позднее отдельно | languages |
| OD-14 | Reader accounts/comments | остаются out of scope | product |

До закрытия решения код использует интерфейс/adapter и безопасный default, явно указанный здесь; нельзя зашивать provider-specific поведение в домен.

