"""Celery entrypoints. Each task drives one pass of docs/05 §1's
`discover -> fetch -> normalize -> checkpoint` pipeline for a single source.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
from common.db import create_engine, create_session_factory
from common.hashing import sha256_hex
from common.logging import configure_logging, get_logger
from common.time import utc_now
from integrator_domain.models import Source, SourceSnapshot
from sqlalchemy import select

from source_worker.api import collect_api_source
from source_worker.celery_app import app, settings
from source_worker.fetcher import fetch_feed
from source_worker.html import collect_html_source
from source_worker.ingestion import ingest_candidates
from source_worker.rss import parse_rss_feed
from source_worker.state import record_run

configure_logging(settings.log_level)
logger = get_logger(__name__)


@app.task(name="source_worker.poll_source")  # type: ignore[untyped-decorator]
def poll_source(source_id: str) -> dict[str, int]:
    return asyncio.run(_poll_source(UUID(source_id)))


@app.task(name="source_worker.poll_all_active_sources")  # type: ignore[untyped-decorator]
def poll_all_active_sources() -> list[str]:
    return asyncio.run(_dispatch_active_sources())


async def _poll_source(source_id: UUID) -> dict[str, int]:
    # A fresh engine per invocation: asyncpg connections are bound to the
    # event loop that opened them, and `asyncio.run()` creates a new loop
    # on every call, so a module-level engine would fail on the 2nd+ task
    # run in the same worker process ("attached to a different loop").
    engine = create_engine(settings.database_url)
    try:
        session_factory = create_session_factory(engine)

        async with session_factory() as session:
            source = await session.get(Source, source_id)

        if source is None or not source.is_active:
            logger.warning("source_poll_skipped", source_id=str(source_id))
            return {"created": 0, "duplicates": 0}

        if source.adapter_type == "html":
            async with httpx.AsyncClient(follow_redirects=True) as client:
                candidates, etag, last_modified, error = await collect_html_source(
                    client,
                    source_id=source_id,
                    list_url=source.feed_url,
                    config=source.config,
                    fetched_at=utc_now(),
                    user_agent=settings.http_user_agent,
                    timeout_seconds=settings.http_timeout_seconds,
                )
            if error:
                await record_run(session_factory, source_id, "failed", 0, error)
                return {"created": 0, "duplicates": 0}
            body = b""
            result_etag, result_last_modified = etag, last_modified
        elif source.adapter_type == "api":
            async with httpx.AsyncClient(follow_redirects=True) as client:
                candidates, error = await collect_api_source(
                    client,
                    source_id=source_id,
                    base_url=source.feed_url,
                    config=source.config,
                    fetched_at=utc_now(),
                    user_agent=settings.http_user_agent,
                    timeout_seconds=settings.http_timeout_seconds,
                )
            if error:
                await record_run(session_factory, source_id, "failed", 0, error)
                return {"created": 0, "duplicates": 0}
            body = b""
            result_etag, result_last_modified = None, None
        else:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                result = await fetch_feed(
                    client,
                    source.feed_url,
                    user_agent=settings.http_user_agent,
                    timeout_seconds=settings.http_timeout_seconds,
                    etag=source.etag,
                    last_modified=source.last_modified,
                )

        if source.adapter_type not in {"html", "api"} and result.status == "not_modified":
            await record_run(session_factory, source_id, "not_modified", 0, None)
            logger.info("source_poll_not_modified", source_id=str(source_id))
            return {"created": 0, "duplicates": 0}

        if source.adapter_type not in {"html", "api"} and result.status != "ok":
            await record_run(session_factory, source_id, "failed", 0, result.error)
            logger.warning(
                "source_fetch_failed",
                source_id=str(source_id),
                status=result.status,
                error=result.error,
            )
            return {"created": 0, "duplicates": 0}

        if source.adapter_type not in {"html", "api"}:
            body = result.body or b""
            result_etag, result_last_modified = result.etag, result.last_modified
        adapter_type = source.adapter_type
        async with session_factory() as session, session.begin():
            source = await session.get(Source, source_id)
            if source is not None:
                source.etag = result_etag
                source.last_modified = result_last_modified
                source.last_error = None
                source.consecutive_failures = 0
                session.add(
                    SourceSnapshot(
                        source_id=source_id,
                        status="ok",
                        body=body.decode("utf-8", errors="replace"),
                        content_hash=sha256_hex(body.decode("utf-8", errors="replace")),
                        etag=result_etag,
                        last_modified=result_last_modified,
                    )
                )

        if adapter_type == "rss":
            candidates = parse_rss_feed(body, source_id=source_id, fetched_at=utc_now())
        candidates = candidates[: settings.max_candidates_per_poll]

        stats = await ingest_candidates(session_factory, candidates)
        await record_run(session_factory, source_id, "succeeded", stats.created, None)
        logger.info(
            "source_poll_completed",
            source_id=str(source_id),
            candidates=len(candidates),
            created=stats.created,
            duplicates=stats.duplicates,
        )
        return {"created": stats.created, "duplicates": stats.duplicates}
    finally:
        await engine.dispose()


async def _dispatch_active_sources() -> list[str]:
    engine = create_engine(settings.database_url)
    try:
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            result = await session.execute(select(Source.id).where(Source.is_active))
            source_ids = [str(row[0]) for row in result.all()]
    finally:
        await engine.dispose()

    for source_id in source_ids:
        poll_source.delay(source_id)
    return source_ids
