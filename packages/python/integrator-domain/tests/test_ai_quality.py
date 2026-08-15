from __future__ import annotations
# ruff: noqa
from uuid import uuid4
import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_domain.ai_quality import budget_allowed, promote, rollback
from integrator_domain.models.ai import AIConfigRelease, AIQualityPolicy, PromptTemplate, PromptVersion

@pytest.mark.asyncio
async def test_quality_gate_canary_rollback_and_budget() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    async with factory() as session, session.begin():
        template = PromptTemplate(operation="draft"); session.add(template); await session.flush()
        prompt = PromptVersion(template_id=template.id, version=1, system_prompt="s", user_prompt="u", output_schema="draft"); session.add(prompt); await session.flush()
        session.add(AIQualityPolicy(operation="draft", minimum_score=.8, canary_percent=10, budget_usd=1))
        failed = AIConfigRelease(prompt_version_id=prompt.id, provider="fake", model="v1", audit={"operation":"draft"}); session.add(failed); await promote(session, failed, .7); assert failed.status == "rejected"
        active = AIConfigRelease(prompt_version_id=prompt.id, provider="fake", model="v1", status="active", audit={"operation":"draft"}); session.add(active); await session.flush()
        release = AIConfigRelease(prompt_version_id=prompt.id, provider="fake", model="v2", audit={"operation":"draft"}); session.add(release); await promote(session, release, .9); assert release.status == "canary" and release.rollout_percent == 10
        await rollback(session, release); assert active.status == "active" and not budget_allowed(2, 1)
    await engine.dispose()
