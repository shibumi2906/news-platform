from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_api.main import create_app
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("INSTANCE_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("INSTANCE_TYPE", "integrator")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = create_app()
    app.state.session_factory = create_session_factory(engine)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    await engine.dispose()


async def test_topic_configuration_is_created_updated_and_deactivated(
    client: httpx.AsyncClient,
) -> None:
    payload = {
        "name": "Space industry",
        "slug": "space-industry",
        "categories": [
            {"name": "Launches", "slug": "launches", "keywords": ["launch"]},
            {
                "name": "Commercial",
                "slug": "commercial",
                "parent_slug": "launches",
                "keywords": ["company"],
            },
        ],
        "keywords": ["rocket", "launch"],
        "exclusions": ["game launch"],
        "regions": ["Europe"],
        "priority": 10,
        "relevance_threshold": 0.65,
        "additional_rules": {"minimum_keyword_matches": 1},
    }
    created = await client.post("/api/v1/ai/topics", json=payload)
    assert created.status_code == 201
    topic_id = created.json()["id"]
    payload["priority"] = 20
    updated = await client.put(f"/api/v1/ai/topics/{topic_id}", json=payload)
    assert updated.status_code == 200
    assert updated.json()["priority"] == 20
    assert len((await client.get("/api/v1/ai/topics?active_only=true")).json()) == 1
    assert (await client.delete(f"/api/v1/ai/topics/{topic_id}")).status_code == 204
    assert (await client.get("/api/v1/ai/topics?active_only=true")).json() == []


async def test_topic_rejects_unknown_parent_category(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/ai/topics",
        json={
            "name": "Invalid",
            "slug": "invalid",
            "categories": [
                {"name": "Child", "slug": "child", "parent_slug": "missing"}
            ],
        },
    )
    assert response.status_code == 422


async def test_prompt_versions_activate_only_latest(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/ai/prompts",
        json={
            "operation": "relevance",
            "system_prompt": "Classify safely",
            "user_prompt": "Use supplied topics",
            "output_schema": "RelevanceOutput",
        },
    )
    assert created.status_code == 201
    template_id = created.json()["template_id"]
    second = await client.post(
        f"/api/v1/ai/prompts/{template_id}/versions",
        json={
            "system_prompt": "Classify safely v2",
            "user_prompt": "Use supplied topics and rules",
            "output_schema": "RelevanceOutput",
        },
    )
    assert second.status_code == 201
    assert second.json()["active_version"] == 2
    listed = (await client.get("/api/v1/ai/prompts")).json()
    assert listed[0]["active_version"] == 2
    assert "system_prompt" not in listed[0]
