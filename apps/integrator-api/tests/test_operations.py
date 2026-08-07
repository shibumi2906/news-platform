from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_api.main import create_app
from integrator_domain.models import AIOperationRun, PromptTemplate, PromptVersion
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
    factory = create_session_factory(engine)
    app.state.session_factory = factory
    async with factory() as session, session.begin():
        template = PromptTemplate(operation="translation")
        session.add(template)
        await session.flush()
        prompt = PromptVersion(
            template_id=template.id,
            version=1,
            system_prompt="system",
            user_prompt="user",
            output_schema="TranslationOutput",
            is_active=True,
        )
        session.add(prompt)
        await session.flush()
        session.add(
            AIOperationRun(
                operation="translation",
                provider="fake",
                model="deterministic-v1",
                prompt_version_id=prompt.id,
                status="failed",
                input_hash="a" * 64,
                output={"body": "must not be exposed"},
                error_code="provider_timeout",
                prompt_tokens=10,
                completion_tokens=2,
                latency_ms=500,
                estimated_cost_usd=0.01,
            )
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    await engine.dispose()


async def test_ai_telemetry_is_protected_and_redacted(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/admin/ai-runs")).status_code == 401
    response = await client.get(
        "/api/v1/admin/ai-runs", headers={"X-Admin-Token": "test-admin-token"}
    )
    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["error_code"] == "provider_timeout"
    assert payload["prompt_tokens"] == 10
    assert "output" not in payload
    assert "input_hash" not in payload


async def test_package_read_model_is_protected(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/admin/packages", headers={"X-Admin-Token": "test-admin-token"}
    )
    assert response.status_code == 200
    assert response.json() == []
