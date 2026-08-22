# ADR-007: S3-совместимое хранение медиа

**Статус:** Accepted

## Решение

Медиа хранится через S3-compatible interface; PostgreSQL хранит metadata/provenance/rights, но не крупные blobs.

## Последствия

Self-hosted/cloud profiles взаимозаменяемы; buckets/credentials изолированы по установкам; default backend — OD-03.

