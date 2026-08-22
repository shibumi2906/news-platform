from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from common.db import Base, create_engine, create_session_factory, session_scope
from site_domain.models import (
    IncomingPackage,
    IncomingPackageVersion,
    IngestionAttempt,
    IntegratorConnection,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def engine() -> AsyncEngine:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine


async def test_incoming_package_version_is_unique_per_package_and_version(
    engine: AsyncEngine,
) -> None:
    session_factory = create_session_factory(engine)
    connection_id = uuid.uuid4()
    package_id = uuid.uuid4()

    async with session_scope(session_factory) as session:
        session.add(
            IntegratorConnection(id=connection_id, name="Example Integrator", hmac_secret="s3cr3t")
        )
        incoming_package_id = uuid.uuid4()
        session.add(
            IncomingPackage(
                id=incoming_package_id,
                connection_id=connection_id,
                package_id=package_id,
                latest_version=1,
            )
        )
        session.add(
            IncomingPackageVersion(
                incoming_package_id=incoming_package_id,
                package_version=1,
                payload={"package_id": str(package_id), "package_version": 1},
            )
        )
        await session.commit()

    async with session_scope(session_factory) as session:
        stored = (await session.execute(select(IncomingPackage))).scalar_one()
        assert stored.latest_version == 1
        version = (await session.execute(select(IncomingPackageVersion))).scalar_one()
        assert version.payload["package_version"] == 1


async def test_ingestion_attempt_persists_idempotency_key(engine: AsyncEngine) -> None:
    session_factory = create_session_factory(engine)
    connection_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_scope(session_factory) as session:
        session.add(
            IntegratorConnection(id=connection_id, name="Example Integrator", hmac_secret="s3cr3t")
        )
        session.add(
            IngestionAttempt(
                connection_id=connection_id,
                idempotency_key="key-1",
                request_body_hash="abc123",
                package_id=uuid.uuid4(),
                package_version=1,
                status="accepted",
                response_body={"status": "accepted", "received_at": now.isoformat()},
            )
        )
        await session.commit()

    async with session_scope(session_factory) as session:
        stored = (await session.execute(select(IngestionAttempt))).scalar_one()
        assert stored.idempotency_key == "key-1"
        assert stored.response_body["status"] == "accepted"
