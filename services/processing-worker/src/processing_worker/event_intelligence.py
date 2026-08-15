"""Provider-neutral semantic candidate retrieval and explainable clustering."""
# ruff: noqa: E501

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from integrator_domain.models import Event, EventClusteringPolicy, EventMaterial, SourceMaterial
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class EmbeddingProvider(Protocol):
    """Keeps retrieval independent from a particular vector/AI provider."""

    def embed(self, text: str) -> dict[str, float]: ...


class TokenEmbeddingProvider:
    """Deterministic local baseline; replaceable by an external embedding adapter."""

    def embed(self, text: str) -> dict[str, float]:
        tokens = re.findall(r"[\w'-]{3,}", text.casefold(), flags=re.UNICODE)
        counts: dict[str, float] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0.0) + 1.0
        return counts


@dataclass(frozen=True)
class ClusterDecision:
    event_id: UUID | None
    action: str
    score: float
    evidence: dict[str, object]


async def clustering_policy(session: AsyncSession) -> EventClusteringPolicy:
    policy = await session.scalar(select(EventClusteringPolicy).order_by(EventClusteringPolicy.created_at))
    if policy is None:
        policy = EventClusteringPolicy()
        session.add(policy)
        await session.flush()
    return policy


async def decide_cluster(
    session: AsyncSession,
    material: SourceMaterial,
    *,
    event_key: str,
    entity_names: list[str],
    provider: EmbeddingProvider | None = None,
) -> ClusterDecision:
    provider = provider or TokenEmbeddingProvider()
    policy = await clustering_policy(session)
    window_start = material.published_at - timedelta(hours=policy.candidate_window_hours)
    window_end = material.published_at + timedelta(hours=policy.candidate_window_hours)
    rows = (
        await session.execute(
            select(Event, SourceMaterial)
            .join(EventMaterial, EventMaterial.event_id == Event.id)
            .join(SourceMaterial, SourceMaterial.id == EventMaterial.source_material_id)
            .where(
                Event.status == "active",
                SourceMaterial.published_at.between(window_start, window_end),
                SourceMaterial.id != material.id,
            )
        )
    ).all()
    incoming_vector = provider.embed(_material_text(material))
    incoming_entities = {name.casefold() for name in entity_names if name.strip()}
    best: ClusterDecision | None = None
    for event, candidate in rows:
        cosine = _cosine(incoming_vector, provider.embed(_material_text(candidate)))
        candidate_entities = await _event_entities(session, event.id)
        overlap = sorted(incoming_entities & candidate_entities)
        conflict = bool(incoming_entities and candidate_entities and not overlap)
        exact_key = event.cluster_key == event_key
        score = max(cosine, 0.97 if exact_key else 0.0)
        if overlap:
            score = min(1.0, score + min(0.16, 0.08 * len(overlap)))
        if conflict:
            score = min(score, policy.review_threshold - 0.01)
        evidence: dict[str, object] = {
            "retrieval": "time_window+semantic_embedding+entities",
            "semantic_similarity": round(cosine, 4),
            "event_key_match": exact_key,
            "entity_overlap": overlap,
            "entity_conflict": conflict,
            "candidate_material_id": str(candidate.id),
            "thresholds": {"auto_merge": policy.auto_merge_threshold, "review": policy.review_threshold},
        }
        action = "auto_merge" if score >= policy.auto_merge_threshold and not conflict else "review" if score >= policy.review_threshold else "separate"
        decision = ClusterDecision(event.id, action, score, evidence)
        if best is None or decision.score > best.score:
            best = decision
    return best or ClusterDecision(None, "separate", 0.0, {"retrieval": "no_candidate"})


def _material_text(material: SourceMaterial) -> str:
    return "\n".join(value for value in (material.title, material.excerpt or "", material.body or "") if value)


async def _event_entities(session: AsyncSession, event_id: UUID) -> set[str]:
    from integrator_domain.models import ExtractedEntity

    rows = (
        await session.execute(
            select(ExtractedEntity.normalized_name)
            .join(EventMaterial, EventMaterial.source_material_id == ExtractedEntity.source_material_id)
            .where(EventMaterial.event_id == event_id)
        )
    ).scalars()
    return set(rows)


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0.0) for key, value in left.items())
    norm = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(sum(value * value for value in right.values()))
    return dot / norm if norm else 0.0
