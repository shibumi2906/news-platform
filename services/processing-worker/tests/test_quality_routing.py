from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_domain.ai_quality import rollback
from integrator_domain.models import (
    AIConfigRelease,
    AIQualityPolicy,
    PromptTemplate,
    PromptVersion,
)
from processing_worker.ai_gateway import (
    AIGatewayError,
    AIProviderError,
    AIRequest,
    FakeAIProvider,
    ProviderResponse,
)
from processing_worker.config import Settings
from processing_worker.provider_factory import QualityRoutedGateway, _select_release
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

DRAFT_INPUT = {"materials": [{"title": "Title", "body": "Body"}]}


@pytest.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("INSTANCE_ID", str(uuid.uuid4()))
    monkeypatch.setenv("INSTANCE_TYPE", "integrator")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("AI_PROVIDERS", "fake")
    return Settings.from_env()


async def _release(
    factory: async_sessionmaker[AsyncSession],
    *,
    status: str = "active",
    model: str = "approved-v1",
    rollout: int = 100,
    policy_budget: float | None = None,
) -> AIConfigRelease:
    async with factory() as session, session.begin():
        template = PromptTemplate(operation="draft")
        session.add(template)
        await session.flush()
        prompt = PromptVersion(
            template_id=template.id,
            version=1,
            system_prompt="approved system",
            user_prompt="approved user",
            output_schema="DraftOutput",
            is_active=True,
        )
        session.add(prompt)
        await session.flush()
        release = AIConfigRelease(
            prompt_version_id=prompt.id,
            provider="fake",
            model=model,
            status=status,
            rollout_percent=rollout,
            eval_score=0.95,
            audit={"operation": "draft"},
        )
        session.add(release)
        if policy_budget is not None:
            session.add(
                AIQualityPolicy(
                    operation="draft",
                    minimum_score=0.8,
                    canary_percent=10,
                    budget_usd=policy_budget,
                )
            )
        await session.flush()
        return release


async def test_active_release_selects_approved_model(
    factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    release = await _release(factory)
    gateway = QualityRoutedGateway(settings, factory, [FakeAIProvider()])
    response = await gateway.complete(AIRequest("draft", "legacy", "legacy", DRAFT_INPUT))
    assert response.model == "approved-v1"
    assert response.release_id == release.id


async def test_canary_selection_is_deterministic_and_distributes() -> None:
    active = AIConfigRelease(
        id=uuid.uuid4(),
        prompt_version_id=uuid.uuid4(),
        provider="fake",
        model="active",
        status="active",
        rollout_percent=100,
        audit={"operation": "draft"},
    )
    canary = AIConfigRelease(
        id=uuid.uuid4(),
        prompt_version_id=uuid.uuid4(),
        provider="fake",
        model="canary",
        status="canary",
        rollout_percent=50,
        audit={"operation": "draft"},
    )
    selections = []
    for index in range(100):
        request = AIRequest("draft", "", "", {"material_id": index})
        first = _select_release(request, [active, canary])
        second = _select_release(request, [active, canary])
        assert first is second
        selections.append(first.model if first else None)
    assert {"active", "canary"}.issubset(selections)


class _CostlyProvider:
    name = "fake"
    model = "costly"

    async def complete(self, request: AIRequest) -> ProviderResponse:
        return ProviderResponse({}, 1, 1, estimated_cost_usd=2.0)


class _FailingProvider:
    name = "fake"
    model = "routed-failure"

    async def complete(self, request: AIRequest) -> ProviderResponse:
        raise AIProviderError("routed_failure")


async def test_budget_reaches_gateway_and_rejects_cost(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _release(factory, model="costly", policy_budget=1.0)
    monkeypatch.setattr(
        "processing_worker.provider_factory._provider",
        lambda settings, name, model: _CostlyProvider(),
    )
    gateway = QualityRoutedGateway(settings, factory, [FakeAIProvider()])
    with pytest.raises(AIGatewayError, match="budget_exceeded"):
        await gateway.complete(AIRequest("draft", "", "", {}))


async def test_routed_provider_failure_falls_back(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _release(factory, model="routed-failure")
    monkeypatch.setattr(
        "processing_worker.provider_factory._provider",
        lambda settings, name, model: _FailingProvider(),
    )
    gateway = QualityRoutedGateway(settings, factory, [FakeAIProvider()])
    response = await gateway.complete(AIRequest("draft", "", "", DRAFT_INPUT))
    assert response.model == "deterministic-v1"


async def test_no_active_release_fails_closed_once_policy_exists(
    factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    async with factory() as session, session.begin():
        session.add(
            AIQualityPolicy(
                operation="draft", minimum_score=0.8, canary_percent=10, budget_usd=0
            )
        )
    gateway = QualityRoutedGateway(settings, factory, [FakeAIProvider()])
    with pytest.raises(AIGatewayError, match="no_active_release"):
        await gateway.complete(AIRequest("draft", "", "", {}))


async def test_rollback_restores_previous_approved_route(
    factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    old = await _release(factory, model="approved-old")
    async with factory() as session, session.begin():
        current = await session.get(AIConfigRelease, old.id)
        assert current is not None
        current.status = "active"
        candidate = AIConfigRelease(
            prompt_version_id=current.prompt_version_id,
            provider="fake",
            model="candidate",
            status="canary",
            rollout_percent=100,
            previous_release_id=current.id,
            audit={"operation": "draft"},
        )
        session.add(candidate)
        await session.flush()
        await rollback(session, candidate)
    gateway = QualityRoutedGateway(settings, factory, [FakeAIProvider()])
    response = await gateway.complete(AIRequest("draft", "", "", DRAFT_INPUT))
    assert response.model == "approved-old"
