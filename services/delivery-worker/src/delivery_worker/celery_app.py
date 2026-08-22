from __future__ import annotations

from common.celery_app import create_celery_app

from delivery_worker.config import Settings

settings = Settings.from_env()

app = create_celery_app(
    "delivery-worker", redis_url=settings.redis_url, include=["delivery_worker.tasks"]
)
app.conf.beat_schedule = {
    "deliver-pending-canonical-news-packages": {
        "task": "delivery_worker.process_pending_deliveries",
        "schedule": settings.poll_interval_seconds,
    }
}
