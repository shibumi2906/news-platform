from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.dashboard import enqueue_metric, export_due, reconcile
from site_domain.models import (
    DashboardExportAttempt,
    DashboardOutbox,
    IncomingPackage,
    IncomingPackageVersion,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _enqueue(factory: async_sessionmaker[AsyncSession], key: str = "metric-1") -> None:
    async with factory() as session:
        await enqueue_metric(
            session,
            event_type="package.received",
            metric="packages_received",
            occurred_at=datetime.now(UTC),
            idempotency_key=key,
        )
        await session.commit()


async def test_successful_export_and_idempotency(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        first = await enqueue_metric(
            session,
            event_type="package.received",
            metric="packages_received",
            occurred_at=datetime.now(UTC),
            idempotency_key="same-source-fact",
        )
        second = await enqueue_metric(
            session,
            event_type="package.received",
            metric="packages_received",
            occurred_at=datetime.now(UTC),
            idempotency_key="same-source-fact",
        )
        await session.commit()
        assert first.id == second.id

    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await export_due(
            session_factory,
            dashboard_url="https://dashboard.example/events",
            dashboard_key="secret",
            site_instance_id="site-a",
            client=client,
            batch_size=10,
            retry_base_seconds=1,
        )
    assert result == {"exported": 1, "retrying": 0, "failed": 0}
    assert len(requests) == 1
    assert requests[0].headers["Idempotency-Key"] == "same-source-fact"
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(DashboardOutbox)) == 1
        assert (await session.scalar(select(DashboardOutbox.status))) == "exported"


async def test_temporary_failure_is_retried_without_duplicate(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _enqueue(session_factory)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls == 1 else 200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await export_due(
            session_factory,
            dashboard_url="https://dashboard.example",
            dashboard_key="secret",
            site_instance_id="site-a",
            client=client,
            batch_size=1,
            retry_base_seconds=1,
        )
        assert first["retrying"] == 1
        async with session_factory() as session:
            row = await session.scalar(select(DashboardOutbox))
            assert row is not None
            assert row.status == "retry_wait"
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        second = await export_due(
            session_factory,
            dashboard_url="https://dashboard.example",
            dashboard_key="secret",
            site_instance_id="site-a",
            client=client,
            batch_size=1,
            retry_base_seconds=1,
        )
    assert second["exported"] == 1
    assert calls == 2
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(DashboardOutbox)) == 1
        assert await session.scalar(select(func.count()).select_from(DashboardExportAttempt)) == 2


async def test_reconciliation_restores_only_missing_outbox_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        package = IncomingPackage(connection_id=uuid4(), package_id=uuid4(), latest_version=1)
        session.add(package)
        await session.flush()
        version = IncomingPackageVersion(
            incoming_package_id=package.id, package_version=1, payload={}
        )
        session.add(version)
        await session.flush()
        await enqueue_metric(
            session,
            event_type="package.received",
            metric="packages_received",
            occurred_at=now,
            idempotency_key=f"package_received:{version.id}",
        )
        await session.commit()
        created = await reconcile(
            session, since=now - timedelta(days=1), until=now + timedelta(days=1)
        )
        assert created == 0
        await session.execute(delete(DashboardOutbox))
        await session.commit()
        created = await reconcile(
            session, since=now - timedelta(days=1), until=now + timedelta(days=1)
        )
        assert created == 1
        again = await reconcile(
            session, since=now - timedelta(days=1), until=now + timedelta(days=1)
        )
        assert again == 0


def test_integrator_and_workers_do_not_define_dashboard_sender() -> None:
    root = Path(__file__).resolve().parents[3]
    prohibited = [
        root / "apps" / "integrator-api",
        root / "services",
    ]
    for directory in prohibited:
        for path in directory.rglob("*.py"):
            assert "SUPABASE_DASHBOARD" not in path.read_text(encoding="utf-8")
            assert "dashboard_url" not in path.read_text(encoding="utf-8")
