"""Shared Celery app factory (ADR-006, OD-01: Celery + Redis).

Every worker builds its app through `create_celery_app` so broker/backend
wiring, serialization and reliability settings stay identical across
services; only the app name and included task modules differ per worker.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from celery import Celery, Task

from common.logging import (
    bind_correlation_id,
    new_correlation_id,
    reset_correlation_id,
)


class CorrelatedTask(Task):  # type: ignore[misc]
    """Bind a safe task/message correlation ID for every worker log."""

    abstract = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        headers = self.request.headers or {}
        candidate = headers.get("correlation_id") or self.request.id
        try:
            correlation_id = str(UUID(str(candidate))) if candidate else new_correlation_id()
        except ValueError:
            correlation_id = new_correlation_id()
        token = bind_correlation_id(correlation_id)
        try:
            return self.run(*args, **kwargs)
        finally:
            reset_correlation_id(token)


def create_celery_app(name: str, *, redis_url: str, include: list[str] | None = None) -> Celery:
    app = Celery(name, broker=redis_url, backend=redis_url, include=include or [])
    app.Task = CorrelatedTask
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_reject_on_worker_lost=True,
        task_track_started=True,
        task_soft_time_limit=270,
        task_time_limit=300,
        broker_transport_options={"visibility_timeout": 3600},
        result_expires=3600,
        worker_soft_shutdown_timeout=30,
        worker_enable_soft_shutdown_on_idle=True,
    )
    return app
