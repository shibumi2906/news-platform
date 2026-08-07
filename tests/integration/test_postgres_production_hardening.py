"""Real PostgreSQL security and reliability invariants after Alembic upgrade."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest
from common.db import create_engine, create_session_factory
from site_domain.models import AdminUser, AuditLog, UnifiedJob
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"), reason="requires POSTGRES_TEST_URL"
)
ROOT = Path(__file__).resolve().parents[2]


async def _run() -> None:
    admin_url = os.environ["POSTGRES_TEST_URL"]
    database_name = f"hardening_{uuid.uuid4().hex}"
    admin = await asyncpg.connect(admin_url)
    engine = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        target = admin_url.rsplit("/", 1)[0] + f"/{database_name}"
        sqlalchemy_url = target.replace("postgresql://", "postgresql+asyncpg://")
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
            env={**os.environ, "DATABASE_URL": sqlalchemy_url},
            check=True,
        )
        engine = create_engine(sqlalchemy_url)
        factory = create_session_factory(engine)
        now = datetime.now(UTC)
        async with factory() as session:
            audit = AuditLog(
                actor_label="security-test",
                action="test.append",
                resource_type="test",
                outcome="success",
                details={},
                created_at=now,
            )
            session.add(audit)
            await session.commit()
            audit_id = audit.id
            with pytest.raises(DBAPIError):
                await session.execute(
                    update(AuditLog).where(AuditLog.id == audit_id).values(outcome="changed")
                )
                await session.commit()
            await session.rollback()
        async with factory() as session:
            with pytest.raises(DBAPIError):
                await session.execute(delete(AuditLog).where(AuditLog.id == audit_id))
                await session.commit()
            await session.rollback()
        async with factory() as session:
            session.add_all(
                [
                    UnifiedJob(
                        queue="test",
                        kind="idempotency",
                        idempotency_key="same-key",
                        status="scheduled",
                        payload={},
                        scheduled_at=now,
                        next_attempt_at=now,
                    ),
                    UnifiedJob(
                        queue="test",
                        kind="idempotency",
                        idempotency_key="same-key",
                        status="scheduled",
                        payload={},
                        scheduled_at=now,
                        next_attempt_at=now,
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
        async with factory() as session:
            session.add(
                UnifiedJob(
                    queue="test",
                    kind="invalid-budget",
                    idempotency_key="invalid-budget",
                    status="scheduled",
                    payload={},
                    scheduled_at=now,
                    next_attempt_at=now,
                    attempt_count=2,
                    max_attempts=1,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
        async with factory() as session:
            session.add_all(
                [
                    AdminUser(
                        username="first-user",
                        display_name="First user",
                        email="same@example.test",
                    ),
                    AdminUser(
                        username="second-user",
                        display_name="Second user",
                        email="same@example.test",
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
    finally:
        if engine is not None:
            await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


def test_postgres_append_only_audit_and_job_idempotency() -> None:
    asyncio.run(_run())
