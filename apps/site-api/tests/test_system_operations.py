from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.api.system import build_job_metrics_collector
from site_api.main import create_app
from site_api.storage import MemoryObjectStorage
from site_domain.models import DeadLetter, DistributionJob, UnifiedJob
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("INSTANCE_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("INSTANCE_TYPE", "site")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ADMIN_API_TOKEN", "operations-token")
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    now = datetime.now(UTC)
    async with factory() as session:
        unified = UnifiedJob(
            queue="distribution",
            kind="publish:telegram",
            idempotency_key="operations-test",
            status="dlq",
            payload={},
            scheduled_at=now,
            next_attempt_at=now,
            attempt_count=3,
            max_attempts=3,
        )
        session.add(unified)
        await session.flush()
        session.add(
            DistributionJob(
                unified_job_id=unified.id,
                channel_id=UUID("11111111-1111-1111-1111-111111111111"),
                article_version_id=UUID("22222222-2222-2222-2222-222222222222"),
                idempotency_key="operations-test",
                status="dlq",
                scheduled_at=now,
                next_attempt_at=now,
                max_attempts=3,
                payload={},
            )
        )
        session.add(
            DeadLetter(
                job_id=unified.id,
                reason_code="timeout",
                diagnostics="payload omitted",
            )
        )
        await session.commit()
    app = create_app()
    app.state.db_engine = engine
    app.state.session_factory = factory
    app.state.metrics_collector = build_job_metrics_collector(factory)
    app.state.object_storage = MemoryObjectStorage()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Admin-Token": "operations-token"},
    ) as test_client:
        yield test_client
    await engine.dispose()


async def test_system_status_dlq_listing_and_replay(client: httpx.AsyncClient) -> None:
    status = await client.get("/api/v1/admin/system/status")
    assert status.status_code == 200
    assert status.json()["jobs"]["dlq"] == 1
    alerts = await client.get("/api/v1/admin/system/alerts")
    assert alerts.json()[0]["code"] == "JOB_DLQ_NONEMPTY"
    letters = (await client.get("/api/v1/admin/system/dlq")).json()
    replayed = await client.post(f"/api/v1/admin/system/dlq/{letters[0]['id']}/replay")
    assert replayed.status_code == 200
    assert replayed.json()["status"] == "scheduled"
    assert replayed.json()["attempt_count"] == 3
    assert replayed.json()["max_attempts"] == 4
    assert (await client.get("/api/v1/admin/system/dlq")).json() == []


async def test_request_and_trace_ids_are_validated_and_metrics_exported(
    client: httpx.AsyncClient,
) -> None:
    request_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    response = await client.get(
        "/health/live",
        headers={
            "X-Request-Id": request_id,
            "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        },
    )
    assert response.headers["x-request-id"] == request_id
    assert response.headers["traceparent"].startswith("00-0123456789abcdef0123456789abcdef-")
    invalid = await client.get("/health/live", headers={"X-Request-Id": "private data"})
    assert invalid.headers["x-request-id"] != "private data"
    metrics = await client.get("/metrics")
    assert "http_requests_total" in metrics.text
    assert 'background_jobs{status="dlq"} 1' in metrics.text
