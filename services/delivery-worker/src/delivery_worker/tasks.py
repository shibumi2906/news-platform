"""Celery entrypoint. Runs one batch of the `canonical_news_package.created`
outbox relay (see `delivery.py`)."""

from __future__ import annotations

import asyncio

import httpx
from common.db import create_engine, create_session_factory
from common.logging import configure_logging, get_logger

from delivery_worker.celery_app import app, settings
from delivery_worker.delivery import process_pending_deliveries

configure_logging(settings.log_level)
logger = get_logger(__name__)


@app.task(name="delivery_worker.process_pending_deliveries")  # type: ignore[untyped-decorator]
def process_pending_deliveries_task() -> dict[str, int]:
    return asyncio.run(_process_pending_deliveries())


async def _process_pending_deliveries() -> dict[str, int]:
    # A fresh engine per invocation: asyncpg connections are bound to the
    # event loop that opened them, and `asyncio.run()` creates a new loop
    # on every call, so a module-level engine would fail on the 2nd+ task
    # run in the same worker process ("attached to a different loop").
    engine = create_engine(settings.database_url)
    try:
        session_factory = create_session_factory(engine)
        async with httpx.AsyncClient() as client:
            stats = await process_pending_deliveries(
                session_factory,
                client,
                batch_size=settings.batch_size,
                http_timeout_seconds=settings.http_timeout_seconds,
                max_delivery_attempts=settings.max_delivery_attempts,
                retry_backoff_seconds=settings.retry_backoff_seconds,
            )
    finally:
        await engine.dispose()

    logger.info(
        "delivery_batch_completed",
        delivered=stats.delivered,
        retrying=stats.retrying,
        skipped_duplicate=stats.skipped_duplicate,
        failed=stats.failed,
        dead_lettered=stats.dead_lettered,
    )
    return {
        "delivered": stats.delivered,
        "retrying": stats.retrying,
        "skipped_duplicate": stats.skipped_duplicate,
        "failed": stats.failed,
        "dead_lettered": stats.dead_lettered,
    }
