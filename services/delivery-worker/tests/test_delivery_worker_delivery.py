from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from delivery_worker.delivery import CANONICAL_PACKAGE_CREATED, process_pending_deliveries
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
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _seed_package(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, int]:
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

        package = CanonicalNewsPackage(
            package_version=1,
            instance_id=uuid.uuid4(),
            event_id=event.id,
            content={
                "title": material.title,
                "canonical_url": material.canonical_url,
                "language": material.language,
            },
            sources=[
                {
                    "source_id": str(source.id),
                    "source_material_id": str(material.id),
                    "external_id": material.external_id,
                    "url": material.url,
                    "published_at": now.isoformat(),
                    "fetched_at": now.isoformat(),
                }
            ],
        )
        session.add(package)
        await session.flush()
        package_id, package_version = package.package_id, package.package_version
    return package_id, package_version


async def _seed_connection(
    session_factory: async_sessionmaker[AsyncSession], *, delivery_url: str, is_active: bool = True
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        connection = SiteConnection(
            name="Example Site",
            delivery_url=delivery_url,
            hmac_secret="s3cret",
            is_active=is_active,
        )
        session.add(connection)
        await session.flush()
        connection_id = connection.id
    return connection_id


async def _seed_outbox_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    package_id: uuid.UUID,
    package_version: int,
    status: str = "pending",
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        outbox_event = OutboxEvent(
            event_type=CANONICAL_PACKAGE_CREATED,
            payload={"package_id": str(package_id), "package_version": package_version},
            status=status,
        )
        session.add(outbox_event)
        await session.flush()
        outbox_event_id = outbox_event.id
    return outbox_event_id


async def test_process_pending_deliveries_delivers_and_marks_processed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    package_id, package_version = await _seed_package(session_factory)
    await _seed_connection(session_factory, delivery_url="https://site.example.com")
    outbox_event_id = await _seed_outbox_event(
        session_factory, package_id=package_id, package_version=package_version
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://site.example.com/api/v1/incoming-news-packages"
        return httpx.Response(202)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    stats = await process_pending_deliveries(
        session_factory, client, batch_size=10, http_timeout_seconds=5.0
    )
    await client.aclose()

    assert stats.delivered == 1
    assert stats.retrying == 0
    assert stats.failed == 0

    async with session_factory() as session:
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        assert outbox_event is not None
        assert outbox_event.status == "processed"

        delivery = (await session.execute(select(Delivery))).scalar_one()
        assert delivery.status == "delivered"
        assert delivery.idempotency_key == f"{package_id}:{package_version}"

        attempts = (await session.execute(select(DeliveryAttempt))).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1
        assert attempts[0].response_status_code == 202


async def test_process_pending_deliveries_leaves_event_pending_when_one_connection_fails(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    package_id, package_version = await _seed_package(session_factory)
    await _seed_connection(session_factory, delivery_url="https://good.example.com")
    await _seed_connection(session_factory, delivery_url="https://bad.example.com")
    outbox_event_id = await _seed_outbox_event(
        session_factory, package_id=package_id, package_version=package_version
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "good.example.com":
            return httpx.Response(202)
        return httpx.Response(500, headers={"Retry-After": "0"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    stats = await process_pending_deliveries(
        session_factory, client, batch_size=10, http_timeout_seconds=5.0
    )
    await client.aclose()

    assert stats.delivered == 0
    assert stats.retrying == 1

    async with session_factory() as session:
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        assert outbox_event is not None
        assert outbox_event.status == "pending"

        deliveries = (await session.execute(select(Delivery))).scalars().all()
        statuses = {d.status for d in deliveries}
        assert statuses == {"delivered", "failed"}

    # Retry: the already-delivered connection must not be hit again, only
    # the failing one, and this time it succeeds.
    calls = {"good": 0, "bad": 0}

    def retry_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "good.example.com":
            calls["good"] += 1
            return httpx.Response(202)
        calls["bad"] += 1
        return httpx.Response(202)

    client = httpx.AsyncClient(transport=httpx.MockTransport(retry_handler))
    stats = await process_pending_deliveries(
        session_factory, client, batch_size=10, http_timeout_seconds=5.0
    )
    await client.aclose()

    assert stats.delivered == 1
    assert calls["good"] == 0
    assert calls["bad"] == 1

    async with session_factory() as session:
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        assert outbox_event is not None
        assert outbox_event.status == "processed"

        deliveries = (await session.execute(select(Delivery))).scalars().all()
        assert all(d.status == "delivered" for d in deliveries)


async def test_process_pending_deliveries_skips_inactive_connections(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    package_id, package_version = await _seed_package(session_factory)
    await _seed_connection(
        session_factory, delivery_url="https://inactive.example.com", is_active=False
    )
    outbox_event_id = await _seed_outbox_event(
        session_factory, package_id=package_id, package_version=package_version
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not deliver to an inactive connection")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    stats = await process_pending_deliveries(
        session_factory, client, batch_size=10, http_timeout_seconds=5.0
    )
    await client.aclose()

    assert stats.delivered == 1
    async with session_factory() as session:
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        assert outbox_event is not None
        assert outbox_event.status == "processed"


async def test_process_pending_deliveries_marks_failed_when_package_missing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    outbox_event_id = await _seed_outbox_event(
        session_factory, package_id=uuid.uuid4(), package_version=1
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not attempt delivery when the package is missing")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    stats = await process_pending_deliveries(
        session_factory, client, batch_size=10, http_timeout_seconds=5.0
    )
    await client.aclose()

    assert stats.failed == 1
    async with session_factory() as session:
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        assert outbox_event is not None
        assert outbox_event.status == "failed"


async def test_process_pending_deliveries_is_a_no_op_when_nothing_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not perform any HTTP call")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    stats = await process_pending_deliveries(
        session_factory, client, batch_size=10, http_timeout_seconds=5.0
    )
    await client.aclose()

    assert stats.delivered == 0
    assert stats.retrying == 0
    assert stats.skipped_duplicate == 0
    assert stats.failed == 0
