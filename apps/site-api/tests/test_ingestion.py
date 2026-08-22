from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from common.db import Base, create_engine, create_session_factory
from common.signing import sign
from common.time import to_iso8601
from contracts.package import CanonicalNewsPackageEnvelope, PackageContent, PackageSourceRef
from site_api.errors import (
    ConnectionNotFoundError,
    IdempotencyConflictError,
    InvalidSignatureError,
    PayloadValidationError,
    ReplayWindowExceededError,
)
from site_api.ingestion import ingest_package
from site_domain.models import IncomingPackage, IncomingPackageVersion, IntegratorConnection
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

SECRET = "s3cret"


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _seed_connection(
    session_factory: async_sessionmaker[AsyncSession], *, is_active: bool = True
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        connection = IntegratorConnection(
            name="Example Integrator", hmac_secret=SECRET, is_active=is_active
        )
        session.add(connection)
        await session.flush()
        return connection.id


def _envelope_body(*, package_id: uuid.UUID | None = None, package_version: int = 1) -> bytes:
    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    envelope = CanonicalNewsPackageEnvelope(
        package_id=package_id or uuid.uuid4(),
        package_version=package_version,
        instance_id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        content=PackageContent(
            title="Headline", canonical_url="https://news.example.com/a", language="en"
        ),
        sources=[
            PackageSourceRef(
                source_id=uuid.uuid4(),
                source_material_id=uuid.uuid4(),
                external_id="ext-1",
                url="https://news.example.com/a",
                published_at=now,
                fetched_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )
    return envelope.model_dump_json().encode("utf-8")


def _headers(
    *, idempotency_key: str, body: bytes, secret: str = SECRET, timestamp: str | None = None
) -> dict[str, str]:
    timestamp = timestamp or to_iso8601(datetime.now(UTC))
    nonce = str(uuid.uuid4())
    signature = sign(
        secret, timestamp=timestamp, nonce=nonce, idempotency_key=idempotency_key, body=body
    )
    return {"timestamp": timestamp, "nonce": nonce, "signature": signature}


async def test_ingest_package_accepts_a_new_package(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connection_id = await _seed_connection(session_factory)
    package_id = uuid.uuid4()
    body = _envelope_body(package_id=package_id)
    idempotency_key = f"{package_id}:1"
    headers = _headers(idempotency_key=idempotency_key, body=body)

    async with session_factory() as session:
        receipt, status_code = await ingest_package(
            session,
            connection_id=connection_id,
            signature=headers["signature"],
            timestamp=headers["timestamp"],
            nonce=headers["nonce"],
            idempotency_key=idempotency_key,
            body=body,
            replay_window_seconds=300.0,
        )

    assert status_code == 201
    assert receipt.status == "accepted"
    assert receipt.package_id == package_id
    assert receipt.package_version == 1

    async with session_factory() as session:
        incoming = (await session.execute(select(IncomingPackage))).scalar_one()
        assert incoming.latest_version == 1
        versions = (await session.execute(select(IncomingPackageVersion))).scalars().all()
        assert len(versions) == 1


async def test_ingest_package_retry_with_same_body_returns_stored_receipt(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connection_id = await _seed_connection(session_factory)
    package_id = uuid.uuid4()
    body = _envelope_body(package_id=package_id)
    idempotency_key = f"{package_id}:1"
    headers = _headers(idempotency_key=idempotency_key, body=body)

    async def _call() -> tuple[object, int]:
        async with session_factory() as session:
            return await ingest_package(
                session,
                connection_id=connection_id,
                signature=headers["signature"],
                timestamp=headers["timestamp"],
                nonce=headers["nonce"],
                idempotency_key=idempotency_key,
                body=body,
                replay_window_seconds=300.0,
            )

    first_receipt, first_status = await _call()
    second_receipt, second_status = await _call()

    assert first_status == second_status == 201
    assert first_receipt == second_receipt

    async with session_factory() as session:
        versions = (await session.execute(select(IncomingPackageVersion))).scalars().all()
        assert len(versions) == 1


async def test_ingest_package_rejects_idempotency_conflict_on_different_body(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connection_id = await _seed_connection(session_factory)
    package_id = uuid.uuid4()
    idempotency_key = f"{package_id}:1"
    first_body = _envelope_body(package_id=package_id)
    first_headers = _headers(idempotency_key=idempotency_key, body=first_body)

    async with session_factory() as session:
        await ingest_package(
            session,
            connection_id=connection_id,
            signature=first_headers["signature"],
            timestamp=first_headers["timestamp"],
            nonce=first_headers["nonce"],
            idempotency_key=idempotency_key,
            body=first_body,
            replay_window_seconds=300.0,
        )

    second_body = _envelope_body(package_id=package_id) + b" "
    second_headers = _headers(idempotency_key=idempotency_key, body=second_body)

    with pytest.raises(IdempotencyConflictError):
        async with session_factory() as session:
            await ingest_package(
                session,
                connection_id=connection_id,
                signature=second_headers["signature"],
                timestamp=second_headers["timestamp"],
                nonce=second_headers["nonce"],
                idempotency_key=idempotency_key,
                body=second_body,
                replay_window_seconds=300.0,
            )


async def test_ingest_package_rejects_invalid_signature(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connection_id = await _seed_connection(session_factory)
    body = _envelope_body()
    headers = _headers(idempotency_key="k1", body=body, secret="wrong-secret")

    with pytest.raises(InvalidSignatureError):
        async with session_factory() as session:
            await ingest_package(
                session,
                connection_id=connection_id,
                signature=headers["signature"],
                timestamp=headers["timestamp"],
                nonce=headers["nonce"],
                idempotency_key="k1",
                body=body,
                replay_window_seconds=300.0,
            )


async def test_ingest_package_rejects_timestamp_outside_replay_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connection_id = await _seed_connection(session_factory)
    body = _envelope_body()
    stale_timestamp = to_iso8601(datetime.now(UTC) - timedelta(hours=1))
    headers = _headers(idempotency_key="k1", body=body, timestamp=stale_timestamp)

    with pytest.raises(ReplayWindowExceededError):
        async with session_factory() as session:
            await ingest_package(
                session,
                connection_id=connection_id,
                signature=headers["signature"],
                timestamp=headers["timestamp"],
                nonce=headers["nonce"],
                idempotency_key="k1",
                body=body,
                replay_window_seconds=300.0,
            )


async def test_ingest_package_rejects_unknown_connection(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    body = _envelope_body()
    headers = _headers(idempotency_key="k1", body=body)

    with pytest.raises(ConnectionNotFoundError):
        async with session_factory() as session:
            await ingest_package(
                session,
                connection_id=uuid.uuid4(),
                signature=headers["signature"],
                timestamp=headers["timestamp"],
                nonce=headers["nonce"],
                idempotency_key="k1",
                body=body,
                replay_window_seconds=300.0,
            )


async def test_ingest_package_rejects_inactive_connection(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connection_id = await _seed_connection(session_factory, is_active=False)
    body = _envelope_body()
    headers = _headers(idempotency_key="k1", body=body)

    with pytest.raises(ConnectionNotFoundError):
        async with session_factory() as session:
            await ingest_package(
                session,
                connection_id=connection_id,
                signature=headers["signature"],
                timestamp=headers["timestamp"],
                nonce=headers["nonce"],
                idempotency_key="k1",
                body=body,
                replay_window_seconds=300.0,
            )


async def test_ingest_package_rejects_malformed_payload(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connection_id = await _seed_connection(session_factory)
    body = b'{"not": "a valid envelope"}'
    headers = _headers(idempotency_key="k1", body=body)

    with pytest.raises(PayloadValidationError):
        async with session_factory() as session:
            await ingest_package(
                session,
                connection_id=connection_id,
                signature=headers["signature"],
                timestamp=headers["timestamp"],
                nonce=headers["nonce"],
                idempotency_key="k1",
                body=body,
                replay_window_seconds=300.0,
            )


async def test_ingest_package_returns_duplicate_for_an_already_stored_version(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connection_id = await _seed_connection(session_factory)
    package_id = uuid.uuid4()
    body = _envelope_body(package_id=package_id, package_version=1)

    first_key = f"{package_id}:1"
    first_headers = _headers(idempotency_key=first_key, body=body)
    async with session_factory() as session:
        await ingest_package(
            session,
            connection_id=connection_id,
            signature=first_headers["signature"],
            timestamp=first_headers["timestamp"],
            nonce=first_headers["nonce"],
            idempotency_key=first_key,
            body=body,
            replay_window_seconds=300.0,
        )

    # Same version, different idempotency key (e.g. a manual resend):
    # detected as a duplicate at the IncomingPackageVersion layer.
    second_key = f"{package_id}:1:resend"
    second_headers = _headers(idempotency_key=second_key, body=body)
    async with session_factory() as session:
        receipt, status_code = await ingest_package(
            session,
            connection_id=connection_id,
            signature=second_headers["signature"],
            timestamp=second_headers["timestamp"],
            nonce=second_headers["nonce"],
            idempotency_key=second_key,
            body=body,
            replay_window_seconds=300.0,
        )

    assert status_code == 200
    assert receipt.status == "duplicate"

    async with session_factory() as session:
        versions = (await session.execute(select(IncomingPackageVersion))).scalars().all()
        assert len(versions) == 1
