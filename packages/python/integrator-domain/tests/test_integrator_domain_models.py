from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from common.db import Base, create_engine, create_session_factory, session_scope
from integrator_domain.models import (
    CanonicalNewsPackage,
    Delivery,
    DeliveryAttempt,
    Event,
    OutboxEvent,
    SiteConnection,
    Source,
    SourceMaterial,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def engine() -> AsyncEngine:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine


async def test_source_material_persists_and_enforces_dedup_constraint(
    engine: AsyncEngine,
) -> None:
    session_factory = create_session_factory(engine)
    now = datetime.now(UTC)
    source_id = uuid.uuid4()

    async with session_scope(session_factory) as session:
        session.add(Source(id=source_id, name="Example Feed", feed_url="https://example.com/rss"))
        session.add(
            SourceMaterial(
                source_id=source_id,
                external_id="12345",
                url="https://example.com/a",
                canonical_url="https://example.com/a",
                canonical_url_hash="hash-a",
                title="Trailer released",
                language="en",
                published_at=now,
                fetched_at=now,
                raw={"guid": "12345"},
            )
        )
        await session.commit()

    async with session_scope(session_factory) as session:
        result = await session.execute(select(SourceMaterial))
        stored = result.scalar_one()
        assert stored.external_id == "12345"
        assert stored.raw == {"guid": "12345"}
        assert stored.created_at is not None


async def test_canonical_news_package_round_trips_json_columns(engine: AsyncEngine) -> None:
    session_factory = create_session_factory(engine)
    now = datetime.now(UTC)
    source_id = uuid.uuid4()
    event_id = uuid.uuid4()
    package_id = uuid.uuid4()

    async with session_scope(session_factory) as session:
        session.add(Source(id=source_id, name="Example Feed", feed_url="https://example.com/rss"))
        session.add(
            SourceMaterial(
                id=uuid.uuid4(),
                source_id=source_id,
                external_id="1",
                url="https://example.com/a",
                canonical_url="https://example.com/a",
                canonical_url_hash="hash-a",
                title="Trailer released",
                language="en",
                published_at=now,
                fetched_at=now,
            )
        )
        session.add(Event(id=event_id, source_material_id=uuid.uuid4(), stage="reported"))
        session.add(
            CanonicalNewsPackage(
                package_id=package_id,
                package_version=1,
                instance_id=uuid.uuid4(),
                event_id=event_id,
                content={
                    "title": "Trailer released",
                    "canonical_url": "https://x",
                    "language": "en",
                },
                sources=[{"source_id": str(source_id)}],
            )
        )
        await session.commit()

    async with session_scope(session_factory) as session:
        result = await session.execute(
            select(CanonicalNewsPackage).where(CanonicalNewsPackage.package_id == package_id)
        )
        stored = result.scalar_one()
        assert stored.rights == {"usage": "link_only"}
        assert stored.content["title"] == "Trailer released"


async def test_delivery_and_outbox_event_persist(engine: AsyncEngine) -> None:
    session_factory = create_session_factory(engine)
    connection_id = uuid.uuid4()

    async with session_scope(session_factory) as session:
        session.add(
            SiteConnection(
                id=connection_id,
                name="Example Site",
                delivery_url="https://site.example.com/ingest",
                hmac_secret="s3cr3t",
            )
        )
        delivery_id = uuid.uuid4()
        session.add(
            Delivery(
                id=delivery_id,
                package_id=uuid.uuid4(),
                package_version=1,
                connection_id=connection_id,
                idempotency_key="key-1",
                status="pending",
            )
        )
        session.add(
            DeliveryAttempt(
                delivery_id=delivery_id,
                attempt_number=1,
                status="failed",
                response_status_code=503,
                error={"reason": "unavailable"},
            )
        )
        session.add(OutboxEvent(event_type="package.delivery_requested", payload={"foo": "bar"}))
        await session.commit()

    async with session_scope(session_factory) as session:
        outbox = (await session.execute(select(OutboxEvent))).scalar_one()
        assert outbox.status == "pending"
        assert outbox.payload == {"foo": "bar"}
