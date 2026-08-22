"""Cross-service integration test: delivery-worker -> Site Ingestion API.

Exercises the real producer (`delivery_worker.client.send_package`, signing
over `contracts.CanonicalNewsPackageEnvelope`) against the real consumer
(the `site_api` FastAPI app, in-process over `httpx.ASGITransport`) to prove
the two services agree on the wire contract (ADR-003, OD-04) without relying
only on each side's own mocked unit tests.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from delivery_worker.client import send_package
from delivery_worker.packaging import package_row_to_envelope
from fastapi import FastAPI
from integrator_domain.models import CanonicalNewsPackage
from site_api.config import Settings
from site_api.main import create_app
from site_domain.models import IncomingPackage, IncomingPackageVersion, IntegratorConnection
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

SECRET = "s3cret"


def _build_site_app(
    monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]
) -> FastAPI:
    monkeypatch.setenv("INSTANCE_ID", "22222222-2222-2222-2222-222222222222")
    monkeypatch.setenv("INSTANCE_TYPE", "site")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    app = create_app()
    # `httpx.ASGITransport` does not drive FastAPI's lifespan, so the state it
    # would normally populate on startup is set directly here instead.
    app.state.settings = Settings.from_env()
    app.state.session_factory = session_factory
    return app


@pytest.fixture
async def site_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _seed_connection(
    session_factory: async_sessionmaker[AsyncSession], *, connection_id: uuid.UUID
) -> None:
    async with session_factory() as session, session.begin():
        session.add(IntegratorConnection(id=connection_id, name="E2E Site", hmac_secret=SECRET))


def _build_package_row() -> CanonicalNewsPackage:
    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    source_id = uuid.uuid4()
    material_id = uuid.uuid4()
    return CanonicalNewsPackage(
        package_id=uuid.uuid4(),
        package_version=1,
        instance_id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        event_stage="reported",
        content={
            "title": "Cross-service headline",
            "canonical_url": "https://news.example.com/a",
            "language": "en",
        },
        sources=[
            {
                "source_id": str(source_id),
                "source_material_id": str(material_id),
                "external_id": "ext-1",
                "url": "https://news.example.com/a",
                "published_at": now.isoformat(),
                "fetched_at": now.isoformat(),
            }
        ],
        facts=[],
        entities=[],
        taxonomy=[],
        language_versions={},
        media=[],
        rights={"usage": "link_only"},
        confidence={"overall": 1.0},
        warnings=[],
        created_at=now,
        updated_at=now,
    )


async def test_delivery_worker_can_deliver_to_a_real_site_api_app(
    monkeypatch: pytest.MonkeyPatch,
    site_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_site_app(monkeypatch, site_session_factory)
    connection_id = uuid.uuid4()
    await _seed_connection(site_session_factory, connection_id=connection_id)

    package = _build_package_row()
    envelope = package_row_to_envelope(package)
    body = envelope.model_dump_json().encode("utf-8")
    idempotency_key = f"{package.package_id}:{package.package_version}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
        result = await send_package(
            client,
            connection_id=connection_id,
            delivery_url="http://testserver",
            hmac_secret=SECRET,
            idempotency_key=idempotency_key,
            body=body,
            timeout_seconds=5.0,
        )

    assert result.status == "delivered"
    assert result.response_status_code == 201

    async with site_session_factory() as session:
        incoming = (await session.execute(select(IncomingPackage))).scalar_one()
        assert incoming.connection_id == connection_id
        assert incoming.package_id == package.package_id

        version = (await session.execute(select(IncomingPackageVersion))).scalar_one()
        assert version.payload["content"]["title"] == "Cross-service headline"


async def test_delivery_worker_retry_is_idempotent_against_a_real_site_api_app(
    monkeypatch: pytest.MonkeyPatch,
    site_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_site_app(monkeypatch, site_session_factory)
    connection_id = uuid.uuid4()
    await _seed_connection(site_session_factory, connection_id=connection_id)

    package = _build_package_row()
    envelope = package_row_to_envelope(package)
    body = envelope.model_dump_json().encode("utf-8")
    idempotency_key = f"{package.package_id}:{package.package_version}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
        first = await send_package(
            client,
            connection_id=connection_id,
            delivery_url="http://testserver",
            hmac_secret=SECRET,
            idempotency_key=idempotency_key,
            body=body,
            timeout_seconds=5.0,
        )
        second = await send_package(
            client,
            connection_id=connection_id,
            delivery_url="http://testserver",
            hmac_secret=SECRET,
            idempotency_key=idempotency_key,
            body=body,
            timeout_seconds=5.0,
        )

    assert first.status == "delivered"
    assert second.status == "delivered"

    async with site_session_factory() as session:
        versions = (await session.execute(select(IncomingPackageVersion))).scalars().all()
        assert len(versions) == 1


async def test_delivery_worker_receives_a_failure_on_signature_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    site_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_site_app(monkeypatch, site_session_factory)
    connection_id = uuid.uuid4()
    await _seed_connection(site_session_factory, connection_id=connection_id)

    package = _build_package_row()
    envelope = package_row_to_envelope(package)
    body = envelope.model_dump_json().encode("utf-8")
    idempotency_key = f"{package.package_id}:{package.package_version}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
        result = await send_package(
            client,
            connection_id=connection_id,
            delivery_url="http://testserver",
            hmac_secret="wrong-secret",
            idempotency_key=idempotency_key,
            body=body,
            timeout_seconds=5.0,
            max_attempts=1,
        )

    assert result.status == "failed"
    assert result.response_status_code == 401

    async with site_session_factory() as session:
        assert (await session.execute(select(IncomingPackage))).scalar_one_or_none() is None
