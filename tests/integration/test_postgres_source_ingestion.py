"""PostgreSQL integration coverage for Integrator source ingestion.

Enable with POSTGRES_TEST_URL pointing at an admin database.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import httpx
import pytest
from common.db import create_engine, create_session_factory
from integrator_api.main import create_app
from integrator_domain.models import Source, SourceMaterial, SourceRun, SourceSnapshot
from source_worker.html import parse_html_document
from source_worker.ingestion import ingest_candidates
from source_worker.state import record_run
from sqlalchemy import func, select

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"), reason="requires POSTGRES_TEST_URL"
)

ROOT = Path(__file__).resolve().parents[2]


async def _run() -> None:
    admin_url = os.environ["POSTGRES_TEST_URL"]
    database_name = f"source_e2e_{uuid.uuid4().hex}"
    admin = await asyncpg.connect(admin_url)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        target_url = admin_url.rsplit("/", 1)[0] + f"/{database_name}"
        sqlalchemy_url = target_url.replace("postgresql://", "postgresql+asyncpg://")
        env = {**os.environ, "DATABASE_URL": sqlalchemy_url}
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "migrations/integrator/alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )

        engine = create_engine(sqlalchemy_url)
        factory = create_session_factory(engine)
        try:
            os.environ.update(
                INSTANCE_ID="11111111-1111-1111-1111-111111111111",
                INSTANCE_TYPE="integrator",
                DATABASE_URL=sqlalchemy_url,
            )
            app = create_app()
            app.state.session_factory = factory
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post(
                    "/api/v1/sources",
                    json={
                        "name": "HTML Source",
                        "feed_url": "https://example.test/news",
                        "adapter_type": "html",
                        "poll_interval_seconds": 120,
                    },
                )
                assert created.status_code == 201
                source_id = uuid.UUID(created.json()["id"])
                assert (await client.get("/api/v1/sources")).json()[0]["status"] == "active"
                assert (
                    await client.post(f"/api/v1/sources/{source_id}/deactivate")
                ).status_code == 200
                assert (
                    await client.post(f"/api/v1/sources/{source_id}/activate")
                ).status_code == 200

            fetched_at = datetime.now(UTC)
            candidates = parse_html_document(
                b"<html><title>Headline</title><body>Story body</body></html>",
                source_id=source_id,
                url="https://example.test/news",
                fetched_at=fetched_at,
            )
            stats = await ingest_candidates(factory, candidates)
            assert stats.created == 1

            async with factory() as session, session.begin():
                session.add(
                    SourceSnapshot(
                        source_id=source_id,
                        status="ok",
                        body="<html>snapshot</html>",
                        content_hash="a" * 64,
                    )
                )
            await record_run(factory, source_id, "succeeded", 1, None)
            await record_run(factory, source_id, "failed", 0, "http_503")

            async with factory() as session:
                source = await session.get(Source, source_id)
                assert source is not None
                assert source.status == "error"
                assert source.consecutive_failures == 1
                assert source.last_error == "http_503"
                assert await session.scalar(select(func.count()).select_from(SourceMaterial)) == 1
                assert await session.scalar(select(func.count()).select_from(SourceRun)) == 2
                assert await session.scalar(select(func.count()).select_from(SourceSnapshot)) == 1

            await record_run(factory, source_id, "succeeded", 0, None)
            async with factory() as session:
                source = await session.get(Source, source_id)
                assert source is not None
                assert source.status == "active"
                assert source.consecutive_failures == 0
                assert source.last_error is None
                assert await session.scalar(select(func.count()).select_from(SourceRun)) == 3
        finally:
            await engine.dispose()
    finally:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


def test_postgres_source_admin_and_worker_ingestion() -> None:
    asyncio.run(_run())
