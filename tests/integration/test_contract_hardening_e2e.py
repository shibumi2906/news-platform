"""Contract v1.1 correction and replay across the real sender/receiver boundary."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from delivery_worker.delivery import CANONICAL_PACKAGE_CREATED, process_pending_deliveries
from integrator_api.main import create_app as create_integrator_app
from integrator_domain.models import (
    CanonicalNewsPackage,
    Event,
    OutboxEvent,
    ReplayRequest,
    SiteConnection,
    Source,
    SourceMaterial,
)
from site_api.config import Settings as SiteSettings
from site_api.main import create_app as create_site_app
from site_domain.models import IncomingPackage, IncomingPackageVersion, IntegratorConnection
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

SECRET = "contract-hardening-secret"


@pytest.fixture
async def factories() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]]
]:
    integrator_engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    site_engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with integrator_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with site_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(integrator_engine), create_session_factory(site_engine)
    await integrator_engine.dispose()
    await site_engine.dispose()


async def test_create_deliver_correct_and_idempotently_replay(
    factories: tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integrator_factory, site_factory = factories
    connection_id = uuid.uuid4()
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    async with integrator_factory() as session, session.begin():
        source = Source(name="Wire", feed_url="https://wire.test/rss")
        session.add(source)
        await session.flush()
        material = SourceMaterial(
            source_id=source.id,
            external_id="one",
            url="https://wire.test/one",
            canonical_url="https://wire.test/one",
            canonical_url_hash="one",
            title="Original",
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
            operation="created",
            content={
                "title": "Original",
                "canonical_url": material.canonical_url,
                "language": "en",
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
        session.add(
            OutboxEvent(
                event_type=CANONICAL_PACKAGE_CREATED,
                payload={"package_id": str(package.package_id), "package_version": 1},
            )
        )
        session.add(
            SiteConnection(
                id=connection_id,
                name="Entertainment",
                delivery_url="http://site",
                hmac_secret=SECRET,
            )
        )
        package_id = package.package_id
    async with site_factory() as session, session.begin():
        session.add(
            IntegratorConnection(
                id=connection_id, name="Integrator", hmac_secret=SECRET
            )
        )

    monkeypatch.setenv("INSTANCE_ID", "22222222-2222-2222-2222-222222222222")
    monkeypatch.setenv("INSTANCE_TYPE", "site")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    site_app = create_site_app()
    site_app.state.settings = SiteSettings.from_env()
    site_app.state.session_factory = site_factory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=site_app), base_url="http://site"
    ) as delivery_client:
        first = await process_pending_deliveries(
            integrator_factory,
            delivery_client,
            batch_size=10,
            http_timeout_seconds=5,
        )
    assert first.delivered == 1

    monkeypatch.setenv("INSTANCE_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("INSTANCE_TYPE", "integrator")
    monkeypatch.setenv("ADMIN_API_TOKEN", "contract-admin-token")
    integrator_app = create_integrator_app()
    integrator_app.state.session_factory = integrator_factory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=integrator_app),
        base_url="http://integrator",
        headers={"X-Admin-Token": "contract-admin-token"},
    ) as admin_client:
        correction = await admin_client.post(
            f"/api/v1/admin/integration/packages/{package_id}/revisions",
            json={
                "operation": "corrected",
                "reason": "Corrected headline",
                "content": {
                    "title": "Corrected",
                    "canonical_url": "https://wire.test/one",
                    "language": "en",
                },
            },
        )
        assert correction.status_code == 201

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=site_app), base_url="http://site"
    ) as delivery_client:
        corrected = await process_pending_deliveries(
            integrator_factory,
            delivery_client,
            batch_size=10,
            http_timeout_seconds=5,
        )
    assert corrected.delivered == 1

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=integrator_app),
        base_url="http://integrator",
        headers={"X-Admin-Token": "contract-admin-token"},
    ) as admin_client:
        replay_payload = {"connection_id": str(connection_id), "package_id": str(package_id)}
        first_replay = await admin_client.post(
            "/api/v1/admin/integration/replays",
            headers={"Idempotency-Key": "e2e-replay"},
            json=replay_payload,
        )
        duplicate_replay = await admin_client.post(
            "/api/v1/admin/integration/replays",
            headers={"Idempotency-Key": "e2e-replay"},
            json=replay_payload,
        )
        assert first_replay.json() == duplicate_replay.json()
        assert first_replay.json()["package_count"] == 2

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=site_app), base_url="http://site"
    ) as delivery_client:
        replayed = await process_pending_deliveries(
            integrator_factory,
            delivery_client,
            batch_size=10,
            http_timeout_seconds=5,
        )
    assert replayed.delivered == 2

    async with site_factory() as session:
        incoming = (await session.execute(select(IncomingPackage))).scalar_one()
        assert incoming.latest_version == 2
        assert await session.scalar(select(func.count()).select_from(IncomingPackageVersion)) == 2
        versions = list(
            (
                await session.execute(
                    select(IncomingPackageVersion).order_by(
                        IncomingPackageVersion.package_version
                    )
                )
            ).scalars()
        )
        assert versions[0].payload["operation"] == "created"
        assert versions[1].payload["operation"] == "corrected"
        assert versions[1].payload["revision_reason"] == "Corrected headline"
    async with integrator_factory() as session:
        assert await session.scalar(select(func.count()).select_from(CanonicalNewsPackage)) == 2
        replay = (await session.execute(select(ReplayRequest))).scalar_one()
        assert replay.status == "completed"
        assert replay.completed_count == 2 and replay.failed_count == 0
