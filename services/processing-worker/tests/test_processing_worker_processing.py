from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_domain.models import (
    CanonicalNewsPackage,
    Event,
    OutboxEvent,
    PromptTemplate,
    PromptVersion,
    Source,
    SourceMaterial,
    Topic,
)
from processing_worker.processing import (
    CANONICAL_PACKAGE_CREATED,
    SOURCE_MATERIAL_INGESTED,
    process_pending_events,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _seed_material_and_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        source = Source(name="Example Newswire", feed_url="https://news.example.com/rss")
        session.add(source)
        await session.flush()

        material = SourceMaterial(
            source_id=source.id,
            external_id="ext-1",
            url="https://news.example.com/a",
            canonical_url="https://news.example.com/a",
            canonical_url_hash="deadbeef",
            title="Headline",
            language="en",
            published_at=now,
            fetched_at=now,
            raw={},
        )
        session.add(material)
        await session.flush()

        event = Event(source_material_id=material.id)
        session.add(event)
        await session.flush()

        session.add(
            Topic(
                name="Headlines",
                slug="headlines",
                keywords=["headline"],
                categories=[{"name": "General", "slug": "general", "keywords": []}],
            )
        )
        for operation, schema in (
            ("relevance", "RelevanceOutput"),
            ("extraction", "ExtractionOutput"),
            ("draft", "DraftOutput"),
        ):
            template = PromptTemplate(operation=operation)
            session.add(template)
            await session.flush()
            session.add(
                PromptVersion(
                    template_id=template.id,
                    version=1,
                    system_prompt=f"{operation} system",
                    user_prompt=f"{operation} user",
                    output_schema=schema,
                    is_active=True,
                )
            )

        material_id, event_id = material.id, event.id
    return material_id, event_id


async def _seed_outbox_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    material_id: uuid.UUID,
    event_id: uuid.UUID,
    status: str = "pending",
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        outbox_event = OutboxEvent(
            event_type=SOURCE_MATERIAL_INGESTED,
            payload={"source_material_id": str(material_id), "event_id": str(event_id)},
            status=status,
        )
        session.add(outbox_event)
        await session.flush()
        outbox_event_id = outbox_event.id
    return outbox_event_id


async def test_process_pending_events_creates_package_and_marks_processed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    material_id, event_id = await _seed_material_and_event(session_factory)
    outbox_event_id = await _seed_outbox_event(
        session_factory, material_id=material_id, event_id=event_id
    )
    instance_id = uuid.uuid4()

    stats = await process_pending_events(session_factory, instance_id=instance_id, batch_size=10)

    assert stats.processed == 1
    assert stats.skipped_duplicate == 0
    assert stats.failed == 0

    async with session_factory() as session:
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        assert outbox_event is not None
        assert outbox_event.status == "processed"

        package = (await session.execute(select(CanonicalNewsPackage))).scalar_one()
        assert package.event_id == event_id
        assert package.instance_id == instance_id
        assert package.package_version == 1

        created_events = (
            (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_type == CANONICAL_PACKAGE_CREATED)
                )
            )
            .scalars()
            .all()
        )
        assert len(created_events) == 1
        assert created_events[0].payload["package_id"] == str(package.package_id)


async def test_process_pending_events_is_a_no_op_when_nothing_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    material_id, event_id = await _seed_material_and_event(session_factory)
    await _seed_outbox_event(session_factory, material_id=material_id, event_id=event_id)

    await process_pending_events(session_factory, instance_id=uuid.uuid4(), batch_size=10)
    second_run = await process_pending_events(
        session_factory, instance_id=uuid.uuid4(), batch_size=10
    )

    assert second_run.processed == 0
    assert second_run.skipped_duplicate == 0
    assert second_run.failed == 0


async def test_process_pending_events_skips_duplicate_when_package_already_exists(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    material_id, event_id = await _seed_material_and_event(session_factory)
    outbox_event_id = await _seed_outbox_event(
        session_factory, material_id=material_id, event_id=event_id
    )
    await process_pending_events(session_factory, instance_id=uuid.uuid4(), batch_size=10)

    # Simulate an out-of-band retry re-marking the same outbox row pending.
    async with session_factory() as session, session.begin():
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        assert outbox_event is not None
        outbox_event.status = "pending"

    stats = await process_pending_events(session_factory, instance_id=uuid.uuid4(), batch_size=10)

    assert stats.processed == 0
    assert stats.skipped_duplicate == 1

    async with session_factory() as session:
        packages = (await session.execute(select(CanonicalNewsPackage))).scalars().all()
    assert len(packages) == 1


async def test_process_pending_events_marks_failed_when_material_missing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    outbox_event_id = await _seed_outbox_event(
        session_factory, material_id=uuid.uuid4(), event_id=uuid.uuid4()
    )

    stats = await process_pending_events(session_factory, instance_id=uuid.uuid4(), batch_size=10)

    assert stats.failed == 1
    async with session_factory() as session:
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        assert outbox_event is not None
        assert outbox_event.status == "failed"
