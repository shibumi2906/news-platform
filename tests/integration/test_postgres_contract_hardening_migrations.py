"""Upgrade and clean-install checks for the contract-hardening migrations."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"), reason="requires POSTGRES_TEST_URL"
)

ROOT = Path(__file__).resolve().parents[2]


def _database_url(admin_url: str, name: str) -> str:
    return admin_url.rsplit("/", 1)[0] + f"/{name}"


def _migrate(config: str, database_url: str, revision: str) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": database_url.replace("postgresql://", "postgresql+asyncpg://"),
        "PYTHONPATH": os.pathsep.join(
            [
                "packages/python/common/src",
                "packages/python/contracts/src",
                "packages/python/integrator-domain/src",
                "packages/python/site-domain/src",
            ]
        ),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", config, "upgrade", revision],
        cwd=ROOT,
        env=env,
        check=True,
    )


async def _run() -> None:
    admin_url = os.environ["POSTGRES_TEST_URL"]
    suffix = uuid.uuid4().hex
    names = {
        "integrator_upgrade": f"contract_integrator_upgrade_{suffix}",
        "integrator_clean": f"contract_integrator_clean_{suffix}",
        "site_upgrade": f"contract_site_upgrade_{suffix}",
        "site_clean": f"contract_site_clean_{suffix}",
    }
    admin = await asyncpg.connect(admin_url)
    try:
        for name in names.values():
            await admin.execute(f'CREATE DATABASE "{name}"')

        integrator_upgrade = _database_url(admin_url, names["integrator_upgrade"])
        _migrate("migrations/integrator/alembic.ini", integrator_upgrade, "d5e1f0a3c782")
        connection = await asyncpg.connect(integrator_upgrade)
        try:
            connection_id = uuid.uuid4()
            delivery_id = uuid.uuid4()
            await connection.execute(
                """
                INSERT INTO site_connection
                    (id, name, delivery_url, hmac_secret, is_active, created_at, updated_at)
                VALUES ($1, 'Legacy', 'https://site.test', 'legacy-secret', true, now(), now())
                """,
                connection_id,
            )
            await connection.execute(
                """
                INSERT INTO delivery
                    (id, package_id, package_version, connection_id, idempotency_key,
                     status, created_at, updated_at)
                VALUES ($1, $2, 1, $3, 'legacy:1', 'pending', now(), now())
                """,
                delivery_id,
                uuid.uuid4(),
                connection_id,
            )
        finally:
            await connection.close()
        _migrate("migrations/integrator/alembic.ini", integrator_upgrade, "head")
        connection = await asyncpg.connect(integrator_upgrade)
        try:
            row = await connection.fetchrow(
                "SELECT active_key_id FROM site_connection WHERE id=$1", connection_id
            )
            delivery = await connection.fetchrow(
                "SELECT attempt_budget_used, manual_retry_count FROM delivery WHERE id=$1",
                delivery_id,
            )
            assert row["active_key_id"] == "legacy"
            assert delivery["attempt_budget_used"] == delivery["manual_retry_count"] == 0
        finally:
            await connection.close()

        integrator_clean = _database_url(admin_url, names["integrator_clean"])
        _migrate("migrations/integrator/alembic.ini", integrator_clean, "head")
        connection = await asyncpg.connect(integrator_clean)
        try:
            assert await connection.fetchval("SELECT to_regclass('replay_request')")
            assert await connection.fetchval("SELECT to_regclass('extracted_geography')")
        finally:
            await connection.close()

        site_upgrade = _database_url(admin_url, names["site_upgrade"])
        _migrate("migrations/site/alembic.ini", site_upgrade, "b2c3d4e5f6a7")
        connection = await asyncpg.connect(site_upgrade)
        try:
            connection_id = uuid.uuid4()
            await connection.execute(
                """
                INSERT INTO integrator_connection
                    (id, name, hmac_secret, is_active, created_at, updated_at)
                VALUES ($1, 'Legacy', 'legacy-secret', true, now(), now())
                """,
                connection_id,
            )
        finally:
            await connection.close()
        _migrate("migrations/site/alembic.ini", site_upgrade, "head")
        connection = await asyncpg.connect(site_upgrade)
        try:
            assert (
                await connection.fetchval(
                    "SELECT active_key_id FROM integrator_connection WHERE id=$1",
                    connection_id,
                )
                == "legacy"
            )
        finally:
            await connection.close()

        site_clean = _database_url(admin_url, names["site_clean"])
        _migrate("migrations/site/alembic.ini", site_clean, "head")
        connection = await asyncpg.connect(site_clean)
        try:
            assert await connection.fetchval("SELECT to_regclass('integrator_connection')")
        finally:
            await connection.close()
    finally:
        for name in names.values():
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=$1 AND pid <> pg_backend_pid()",
                name,
            )
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await admin.close()


def test_contract_hardening_upgrade_and_clean_install() -> None:
    asyncio.run(_run())
