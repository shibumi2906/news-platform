from __future__ import annotations
# ruff: noqa

from collections.abc import AsyncIterator

import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_domain.models import Source
from source_worker.state import record_run
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def test_degradation_pause_and_recovery(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session, session.begin():
        source = Source(name="x", feed_url="https://example.test", config={"pause_after_failures": 2})
        session.add(source); await session.flush(); source_id = source.id
    await record_run(factory, source_id, "failed", 0, "http_429")
    await record_run(factory, source_id, "failed", 0, "parser_drift")
    async with factory() as session:
        source = await session.get(Source, source_id)  # type: ignore[assignment]
        assert source is not None and source.health_status == "paused" and not source.is_active
        source.is_active = True
    await record_run(factory, source_id, "succeeded", 1, None)
    async with factory() as session:
        source = await session.get(Source, source_id)  # type: ignore[assignment]
        assert source is not None and source.health_status == "healthy" and source.consecutive_failures == 0
