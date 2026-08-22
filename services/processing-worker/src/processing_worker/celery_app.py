from __future__ import annotations

from common.celery_app import create_celery_app

from processing_worker.config import Settings

settings = Settings.from_env()

app = create_celery_app(
    "processing-worker", redis_url=settings.redis_url, include=["processing_worker.tasks"]
)
app.conf.beat_schedule = {
    "process-pending-source-material-events": {
        "task": "processing_worker.process_pending_events",
        "schedule": settings.poll_interval_seconds,
    }
}
