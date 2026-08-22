"""Shared Celery app factory (ADR-006, OD-01: Celery + Redis).

Every worker builds its app through `create_celery_app` so broker/backend
wiring, serialization and reliability settings stay identical across
services; only the app name and included task modules differ per worker.
"""

from __future__ import annotations

from celery import Celery


def create_celery_app(name: str, *, redis_url: str, include: list[str] | None = None) -> Celery:
    app = Celery(name, broker=redis_url, backend=redis_url, include=include or [])
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_reject_on_worker_lost=True,
    )
    return app
