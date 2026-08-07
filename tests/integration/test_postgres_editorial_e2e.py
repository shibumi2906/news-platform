"""Real PostgreSQL + Alembic editorial lifecycle test.

Set POSTGRES_TEST_URL to a PostgreSQL admin URL (for example the Compose
site database with its database name replaced by ``postgres``) to enable it.
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
from common.signing import sign
from common.time import to_iso8601
from contracts.package import CanonicalNewsPackageEnvelope, PackageContent, PackageSourceRef
from site_api.editorial import (
    create_article_from_package,
    create_version,
    publish,
    review,
    submit_for_review,
    unpublish,
)
from site_api.ingestion import ingest_package
from site_api.main import create_app
from site_domain.models import IntegratorConnection, Publication
from sqlalchemy import select

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"), reason="requires POSTGRES_TEST_URL"
)

ROOT = Path(__file__).resolve().parents[2]
SECRET = "integration-test-secret"


async def _run() -> None:
    admin_url = os.environ["POSTGRES_TEST_URL"]
    database_name = f"editorial_e2e_{uuid.uuid4().hex}"
    admin = await asyncpg.connect(admin_url)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        target_url = admin_url.rsplit("/", 1)[0] + f"/{database_name}"
        env = {
            **os.environ,
            "DATABASE_URL": target_url.replace("postgresql://", "postgresql+asyncpg://"),
        }
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "migrations/site/alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
        engine = create_engine(env["DATABASE_URL"])
        factory = create_session_factory(engine)
        try:
            connection_id = uuid.uuid4()
            async with factory() as session, session.begin():
                session.add(IntegratorConnection(id=connection_id, name="E2E", hmac_secret=SECRET))
            now = datetime.now(UTC)
            package_id = uuid.uuid4()
            envelope = CanonicalNewsPackageEnvelope(
                package_id=package_id,
                package_version=1,
                instance_id=uuid.uuid4(),
                event_id=uuid.uuid4(),
                content=PackageContent(
                    title="E2E", canonical_url="https://example.test/a", language="en"
                ),
                sources=[
                    PackageSourceRef(
                        source_id=uuid.uuid4(),
                        source_material_id=uuid.uuid4(),
                        external_id="e2e",
                        url="https://example.test/a",
                        published_at=now,
                        fetched_at=now,
                    )
                ],
                created_at=now,
                updated_at=now,
            )
            body = envelope.model_dump_json().encode()
            timestamp, nonce, key = to_iso8601(now), str(uuid.uuid4()), f"{package_id}:1"
            async with factory() as session:
                await ingest_package(
                    session,
                    connection_id=connection_id,
                    signature=sign(
                        SECRET, timestamp=timestamp, nonce=nonce, idempotency_key=key, body=body
                    ),
                    timestamp=timestamp,
                    nonce=nonce,
                    idempotency_key=key,
                    body=body,
                    replay_window_seconds=300,
                )
                result = await session.execute(
                    select(
                        __import__(
                            "site_domain.models", fromlist=["IncomingPackageVersion"]
                        ).IncomingPackageVersion
                    )
                )
                incoming_version = result.scalar_one()
            async with factory() as session:
                article = await create_article_from_package(
                    session, incoming_package_version_id=incoming_version.id, actor_id="writer"
                )
                article = await create_version(
                    session,
                    article_id=article.id,
                    content={"title": "Corrected"},
                    actor_id="writer",
                    expected_lock_version=article.lock_version,
                )
                article = await submit_for_review(
                    session,
                    article_id=article.id,
                    actor_id="writer",
                    expected_lock_version=article.lock_version,
                )
                article = await review(
                    session,
                    article_id=article.id,
                    actor_id="editor",
                    expected_lock_version=article.lock_version,
                    approve=False,
                    reason="revise",
                )
                article = await submit_for_review(
                    session,
                    article_id=article.id,
                    actor_id="writer",
                    expected_lock_version=article.lock_version,
                )
                article = await review(
                    session,
                    article_id=article.id,
                    actor_id="editor",
                    expected_lock_version=article.lock_version,
                    approve=True,
                )
                article = await publish(
                    session,
                    article_id=article.id,
                    actor_id="editor",
                    expected_lock_version=article.lock_version,
                )
                published_article_id = article.id
                published_lock_version = article.lock_version
            os.environ.update(
                INSTANCE_ID="22222222-2222-2222-2222-222222222222",
                INSTANCE_TYPE="site",
                DATABASE_URL=env["DATABASE_URL"],
                ADMIN_API_TOKEN="public-web-e2e-token",
            )
            app = create_app()
            app.state.session_factory = factory
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://site"
            ) as client:
                public = await client.get(
                    f"/api/v1/public/articles/{published_article_id}"
                )
                assert public.status_code == 200
                assert public.json()["title"] == "Corrected"
                assert (await client.get("/api/v1/admin/articles")).status_code == 401
                admin_articles = await client.get(
                    "/api/v1/admin/articles",
                    headers={"X-Admin-Token": "public-web-e2e-token"},
                )
                assert admin_articles.status_code == 200
                assert admin_articles.json()[0]["status"] == "published"
            async with factory() as session:
                article = await unpublish(
                    session,
                    article_id=published_article_id,
                    expected_lock_version=published_lock_version,
                )
                assert article.status == "unpublished"
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://site"
            ) as client:
                assert (
                    await client.get(f"/api/v1/public/articles/{published_article_id}")
                ).status_code == 404
            async with factory() as session:
                publication = (await session.execute(select(Publication))).scalar_one()
                assert publication.active_article_version_id is not None
        finally:
            await engine.dispose()
    finally:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


def test_postgres_editorial_lifecycle_with_real_migrations() -> None:
    asyncio.run(_run())
