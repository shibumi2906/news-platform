from __future__ import annotations

from common.celery_app import create_celery_app

from distribution_worker.config import Settings

settings = Settings.from_env()
app = create_celery_app(
    "distribution-worker", redis_url=settings.redis_url, include=["distribution_worker.tasks"]
)
app.conf.beat_schedule = {
    "process-due-distribution-jobs": {
        "task": "distribution_worker.process_due_jobs",
        "schedule": settings.poll_interval_seconds,
    }
}
