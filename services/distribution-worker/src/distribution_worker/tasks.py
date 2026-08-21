from __future__ import annotations

import asyncio

import httpx
from common.db import create_engine, create_session_factory
from common.logging import configure_logging, get_logger

from distribution_worker.adapters import (
    DistributionAdapter,
    FacebookAdapter,
    InstagramAdapter,
    TelegramAdapter,
    TikTokAdapter,
    XAdapter,
    YouTubeAdapter,
)
from distribution_worker.celery_app import app, settings
from distribution_worker.delivery import process_due_jobs

configure_logging(settings.log_level)
logger = get_logger(__name__)


@app.task(name="distribution_worker.process_due_jobs")  # type: ignore[untyped-decorator]
def process_due_jobs_task() -> dict[str, int]:
    return asyncio.run(_run())


async def _run() -> dict[str, int]:
    engine = create_engine(settings.database_url)
    try:
        session_factory = create_session_factory(engine)
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            adapters: dict[str, DistributionAdapter] = {
                "telegram": TelegramAdapter(client, base_url=settings.telegram_base_url),
                "facebook": FacebookAdapter(client, base_url=settings.facebook_base_url),
                "instagram": InstagramAdapter(client, base_url=settings.facebook_base_url),
                "tiktok": TikTokAdapter(client, base_url=settings.tiktok_base_url),
                "x": XAdapter(client, base_url=settings.x_base_url),
                "youtube": YouTubeAdapter(client, base_url=settings.youtube_base_url),
            }
            stats = await process_due_jobs(
                session_factory,
                adapters,
                batch_size=settings.batch_size,
                retry_base_seconds=settings.retry_base_seconds,
            )
    finally:
        await engine.dispose()
    logger.info("distribution_batch_completed", **stats)
    return stats
