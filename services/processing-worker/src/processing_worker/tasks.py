"""Celery entrypoint. Runs one batch of the `source_material.ingested`
outbox relay (see `processing.py`)."""

from __future__ import annotations

import asyncio
from uuid import UUID

from common.db import create_engine, create_session_factory
from common.logging import configure_logging, get_logger

from processing_worker.celery_app import app, settings
from processing_worker.processing import process_pending_events

configure_logging(settings.log_level)
logger = get_logger(__name__)


@app.task(name="processing_worker.process_pending_events")  # type: ignore[untyped-decorator]
def process_pending_events_task() -> dict[str, int]:
    return asyncio.run(_process_pending_events())


async def _process_pending_events() -> dict[str, int]:
    # A fresh engine per invocation: asyncpg connections are bound to the
    # event loop that opened them, and `asyncio.run()` creates a new loop
    # on every call, so a module-level engine would fail on the 2nd+ task
    # run in the same worker process ("attached to a different loop").
    engine = create_engine(settings.database_url)
    try:
        session_factory = create_session_factory(engine)
        stats = await process_pending_events(
            session_factory,
            instance_id=UUID(settings.instance_id),
            batch_size=settings.batch_size,
        )
    finally:
        await engine.dispose()

    logger.info(
        "processing_batch_completed",
        processed=stats.processed,
        skipped_duplicate=stats.skipped_duplicate,
        failed=stats.failed,
    )
    return {
        "processed": stats.processed,
        "skipped_duplicate": stats.skipped_duplicate,
        "failed": stats.failed,
    }
