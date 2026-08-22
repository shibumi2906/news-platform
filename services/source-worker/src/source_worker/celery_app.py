from __future__ import annotations

from common.celery_app import create_celery_app

from source_worker.config import Settings

settings = Settings.from_env()

app = create_celery_app(
    "source-worker", redis_url=settings.redis_url, include=["source_worker.tasks"]
)
app.conf.beat_schedule = {
    "poll-active-sources": {
        "task": "source_worker.poll_all_active_sources",
        "schedule": settings.poll_interval_seconds,
    }
}
