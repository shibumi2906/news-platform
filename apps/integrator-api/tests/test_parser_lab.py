from __future__ import annotations
# ruff: noqa

import httpx
import pytest
from collections.abc import AsyncIterator

from common.db import Base, create_engine, create_session_factory
from integrator_api.main import create_app
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("INSTANCE_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("INSTANCE_TYPE", "integrator")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = create_app()
    app.state.session_factory = create_session_factory(engine)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"X-Admin-Token": "test-admin-token"}) as test_client:
        yield test_client
    await engine.dispose()


async def test_parser_version_requires_validation_approval_and_can_roll_back(client: httpx.AsyncClient) -> None:
    source = await client.post("/api/v1/sources", json={"name": "Parser test", "feed_url": "https://example.test/news", "adapter_type": "html", "config": {"item_selector": "article", "url_selector": "a", "title_selector": "h1", "content_selector": ".content"}})
    assert source.status_code == 201
    source_id = source.json()["id"]
    snapshot = await client.post("/api/v1/parser-lab/snapshots", json={"source_id": source_id, "url": "https://example.test/news", "html": "<article><a href='/one'><h1>One</h1></a><div class='content'>Body</div></article>"})
    assert snapshot.status_code == 201
    payload = {"source_id": source_id, "adapter_type": "html", "snapshot_id": snapshot.json()["id"], "rules": {"item_selector": "article", "url_selector": "a", "title_selector": "h1", "content_selector": ".content"}}
    first = await client.post("/api/v1/parser-lab/versions", json=payload)
    assert first.status_code == 201 and first.json()["status"] == "validated"
    assert (await client.post(f"/api/v1/parser-lab/versions/{first.json()['id']}/approve")).json()["status"] == "active"
    second = await client.post("/api/v1/parser-lab/versions", json=payload)
    assert second.status_code == 201
    assert (await client.post(f"/api/v1/parser-lab/versions/{second.json()['id']}/approve")).status_code == 200
    assert (await client.post(f"/api/v1/parser-lab/versions/{first.json()['id']}/rollback")).json()["status"] == "active"


async def test_parser_lab_blocks_unsafe_snapshot_url(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/parser-lab/snapshots", json={"source_id": "11111111-1111-1111-1111-111111111111", "url": "http://127.0.0.1/", "html": "x"})
    assert response.status_code == 422
