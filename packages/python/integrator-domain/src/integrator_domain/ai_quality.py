"""Provider-neutral quality gates and release state transitions."""
# ruff: noqa
from __future__ import annotations
from integrator_domain.models.ai import AIConfigRelease, AIQualityPolicy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

async def promote(session: AsyncSession, release: AIConfigRelease, score: float) -> AIConfigRelease:
    policy = await session.scalar(select(AIQualityPolicy).where(AIQualityPolicy.operation == release.audit["operation"]))
    minimum = policy.minimum_score if policy else 0.8
    release.eval_score = score
    if score < minimum:
        release.status = "rejected"; release.audit = {**release.audit, "reason": "quality_gate_failed"}; return release
    active = await session.scalar(select(AIConfigRelease).where(AIConfigRelease.status == "active"))
    release.previous_release_id = active.id if active else None
    release.rollout_percent = policy.canary_percent if policy else 10
    release.status = "canary" if release.rollout_percent < 100 else "active"
    return release

async def rollback(session: AsyncSession, release: AIConfigRelease) -> AIConfigRelease:
    release.status = "rolled_back"
    if release.previous_release_id:
        previous = await session.get(AIConfigRelease, release.previous_release_id)
        if previous: previous.status, previous.rollout_percent = "active", 100
    return release

def budget_allowed(cost: float, limit: float) -> bool: return limit <= 0 or cost <= limit
