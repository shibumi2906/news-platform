from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from common.db import Base, create_engine, create_session_factory
from common.signing import (
    CONNECTION_ID_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    sign,
)
from common.time import to_iso8601
from contracts.package import CanonicalNewsPackageEnvelope, PackageContent, PackageSourceRef
from fastapi import FastAPI
from fastapi.testclient import TestClient
from site_api.main import create_app
from site_domain.models import IntegratorConnection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

SECRET = "s3cret"


def _build_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("INSTANCE_ID", "22222222-2222-2222-2222-222222222222")
    monkeypatch.setenv("INSTANCE_TYPE", "site")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    return create_app()


@pytest.fixture
async def sqlite_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _seed_connection(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        connection = IntegratorConnection(name="Example Integrator", hmac_secret=SECRET)
        session.add(connection)
        await session.flush()
        return connection.id


def _envelope_body(package_id: uuid.UUID) -> bytes:
    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    envelope = CanonicalNewsPackageEnvelope(
        package_id=package_id,
        package_version=1,
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


def _signed_headers(
    *, connection_id: uuid.UUID, idempotency_key: str, body: bytes
) -> dict[str, str]:
    timestamp = to_iso8601(datetime.now(UTC))
    nonce = str(uuid.uuid4())
    signature = sign(
        SECRET, timestamp=timestamp, nonce=nonce, idempotency_key=idempotency_key, body=body
    )
    return {
        CONNECTION_ID_HEADER: str(connection_id),
        SIGNATURE_HEADER: signature,
        TIMESTAMP_HEADER: timestamp,
        NONCE_HEADER: nonce,
        IDEMPOTENCY_KEY_HEADER: idempotency_key,
        "Content-Type": "application/json",
    }


async def test_receive_incoming_package_accepts_a_signed_request(
    monkeypatch: pytest.MonkeyPatch, sqlite_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    app = _build_app(monkeypatch)
    connection_id = await _seed_connection(sqlite_session_factory)
    package_id = uuid.uuid4()
    body = _envelope_body(package_id)
    headers = _signed_headers(
        connection_id=connection_id, idempotency_key=f"{package_id}:1", body=body
    )

    with TestClient(app) as client:
        app.state.session_factory = sqlite_session_factory
        response = client.post(
            "/api/v1/incoming-news-packages", content=body, headers=headers
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["package_id"] == str(package_id)
    assert payload["status"] == "accepted"


async def test_receive_incoming_package_rejects_bad_signature(
    monkeypatch: pytest.MonkeyPatch, sqlite_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    app = _build_app(monkeypatch)
    connection_id = await _seed_connection(sqlite_session_factory)
    package_id = uuid.uuid4()
    body = _envelope_body(package_id)
    headers = _signed_headers(
        connection_id=connection_id, idempotency_key=f"{package_id}:1", body=body
    )
    headers[SIGNATURE_HEADER] = "0" * 64

    with TestClient(app) as client:
        app.state.session_factory = sqlite_session_factory
        response = client.post(
            "/api/v1/incoming-news-packages", content=body, headers=headers
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_signature"


async def test_receive_incoming_package_rejects_malformed_connection_id_header(
    monkeypatch: pytest.MonkeyPatch, sqlite_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    app = _build_app(monkeypatch)
    body = _envelope_body(uuid.uuid4())
    headers = _signed_headers(connection_id=uuid.uuid4(), idempotency_key="k1", body=body)
    headers[CONNECTION_ID_HEADER] = "not-a-uuid"

    with TestClient(app) as client:
        app.state.session_factory = sqlite_session_factory
        response = client.post(
            "/api/v1/incoming-news-packages", content=body, headers=headers
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_connection_id"


async def test_receive_incoming_package_rejects_missing_headers_with_error_envelope(
    monkeypatch: pytest.MonkeyPatch, sqlite_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    app = _build_app(monkeypatch)
    body = _envelope_body(uuid.uuid4())

    with TestClient(app) as client:
        app.state.session_factory = sqlite_session_factory
        response = client.post("/api/v1/incoming-news-packages", content=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
