from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from common.db import Base, create_engine, create_session_factory
from contracts.source import SourceCandidate
from integrator_domain.models import Event, OutboxEvent, Source, SourceMaterial
from source_worker.ingestion import ingest_candidates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


def _make_candidate(
    source_id: uuid.UUID, *, external_id: str, canonical_url: str
) -> SourceCandidate:
    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    return SourceCandidate(
        source_id=source_id,
        external_id=external_id,
        url=canonical_url,
        canonical_url=canonical_url,
        title="Headline",
        excerpt="Summary",
        body="Body",
        author="Reporter",
        language="en",
        published_at=now,
        fetched_at=now,
        raw={"foo": "bar"},
    )


async def _insert_source(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        source = Source(name="Example Newswire", feed_url="https://news.example.com/rss")
        session.add(source)
        await session.flush()
        source_id = source.id
    return source_id


async def test_ingest_candidates_creates_material_event_and_outbox_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source_id = await _insert_source(session_factory)
    candidate = _make_candidate(
        source_id, external_id="ext-1", canonical_url="https://news.example.com/a"
    )

    stats = await ingest_candidates(session_factory, [candidate])

    assert stats.created == 1
    assert stats.duplicates == 0

    async with session_factory() as session:
        material = (await session.execute(select(SourceMaterial))).scalar_one()
        event = (await session.execute(select(Event))).scalar_one()
        outbox_event = (await session.execute(select(OutboxEvent))).scalar_one()

    assert material.source_id == source_id
    assert event.source_material_id == material.id
    assert outbox_event.event_type == "source_material.ingested"
    assert outbox_event.payload["source_material_id"] == str(material.id)


async def test_ingest_candidates_is_idempotent_by_external_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source_id = await _insert_source(session_factory)
    candidate = _make_candidate(
        source_id, external_id="ext-1", canonical_url="https://news.example.com/a"
    )

    first = await ingest_candidates(session_factory, [candidate])
    second = await ingest_candidates(session_factory, [candidate])

    assert first.created == 1
    assert second.created == 0
    assert second.duplicates == 1


async def test_ingest_candidates_dedups_by_canonical_url_hash(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source_id = await _insert_source(session_factory)
    first_candidate = _make_candidate(
        source_id, external_id="ext-1", canonical_url="https://news.example.com/a"
    )
    same_url_different_external_id = _make_candidate(
        source_id, external_id="ext-2", canonical_url="https://news.example.com/a"
    )

    await ingest_candidates(session_factory, [first_candidate])
    stats = await ingest_candidates(session_factory, [same_url_different_external_id])

    assert stats.created == 0
    assert stats.duplicates == 1


async def test_ingest_candidates_skips_all_when_source_material_row_is_new(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source_id = await _insert_source(session_factory)
    candidates = [
        _make_candidate(
            source_id, external_id=f"ext-{i}", canonical_url=f"https://news.example.com/{i}"
        )
        for i in range(3)
    ]

    stats = await ingest_candidates(session_factory, candidates)

    assert stats.created == 3
    assert stats.duplicates == 0
