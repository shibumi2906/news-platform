from __future__ import annotations
# ruff: noqa: E501,I001

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
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = create_app()
    app.state.session_factory = create_session_factory(engine)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Admin-Token": "test-admin-token"},
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
            "categories": [{"name": "Child", "slug": "child", "parent_slug": "missing"}],
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


async def test_languages_and_terminology_are_admin_configurable(
    client: httpx.AsyncClient,
) -> None:
    for payload in (
        {
            "code": "en",
            "name": "English",
            "direction": "ltr",
            "translation_enabled": False,
        },
        {
            "code": "he",
            "name": "Hebrew",
            "direction": "rtl",
            "translation_enabled": True,
        },
    ):
        assert (await client.post("/api/v1/ai/languages", json=payload)).status_code == 201
    languages = (await client.get("/api/v1/ai/languages")).json()
    assert {item["direction"] for item in languages} == {"ltr", "rtl"}

    created = await client.post(
        "/api/v1/ai/terminology",
        json={
            "source_language_code": "en",
            "target_language_code": "he",
            "source_term": "Acme",
            "target_term": "אקמי",
        },
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    listed = (
        await client.get("/api/v1/ai/terminology?source_language=en&target_language=he")
    ).json()
    assert listed[0]["target_term"] == "אקמי"
    assert (await client.delete(f"/api/v1/ai/terminology/{entry_id}")).status_code == 204


async def test_terminology_rejects_unknown_or_same_language(
    client: httpx.AsyncClient,
) -> None:
    assert (
        await client.post(
            "/api/v1/ai/terminology",
            json={
                "source_language_code": "en",
                "target_language_code": "en",
                "source_term": "A",
                "target_term": "B",
            },
        )
    ).status_code == 422


async def test_source_url_credentials_are_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/sources",
        json={
            "name": "Unsafe feed",
            "feed_url": "https://user:private-password@example.com/feed.xml",
            "adapter_type": "rss",
            "poll_interval_seconds": 300,
        },
    )
    assert response.status_code == 422
    assert "private-password" not in response.text


async def test_quality_admin_gate_canary_rollback_and_audit(client: httpx.AsyncClient) -> None:
    prompt = await client.post("/api/v1/ai/prompts", json={"operation": "quality-test", "system_prompt": "s", "user_prompt": "u", "output_schema": "draft"})
    assert prompt.status_code == 201
    policy = await client.put("/api/v1/ai/quality/policies/quality-test", json={"operation": "quality-test", "minimum_score": .8, "canary_percent": 10, "budget_usd": 1})
    assert policy.status_code == 200
    eval_set = await client.post("/api/v1/ai/quality/eval-sets", json={"operation": "quality-test", "version": 1, "cases": [{"input": "x", "expected": "y"}]})
    assert eval_set.json()["frozen"]
    failed = await client.post("/api/v1/ai/quality/releases", json={"prompt_version_id": prompt.json()["active_version_id"], "provider": "fake", "model": "v1", "operation": "quality-test", "eval_score": .7})
    assert failed.json()["status"] == "rejected"
    canary = await client.post("/api/v1/ai/quality/releases", json={"prompt_version_id": prompt.json()["active_version_id"], "provider": "fake", "model": "v1", "operation": "quality-test", "eval_score": .9})
    assert canary.json()["status"] == "canary"
    assert (await client.post(f"/api/v1/ai/quality/releases/{canary.json()['id']}/rollback")).json()["status"] == "rolled_back"
