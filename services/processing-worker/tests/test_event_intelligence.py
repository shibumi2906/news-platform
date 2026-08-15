# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_domain.event_intelligence import merge_events, reverse_operation, split_event
from integrator_domain.models import (
    Event,
    EventClusteringPolicy,
    EventClusterOperation,
    EventMaterial,
    Source,
    SourceMaterial,
)
from processing_worker.event_intelligence import decide_cluster
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _material(
    session: AsyncSession, source: Source, external_id: str, title: str
) -> SourceMaterial:
    now = datetime(2026, 8, 7, 12, tzinfo=UTC)
    material = SourceMaterial(
        source_id=source.id,
        external_id=external_id,
        url=f"https://example.test/{external_id}",
        canonical_url=f"https://example.test/{external_id}",
        canonical_url_hash=external_id,
        title=title,
        body=title,
        language="en",
        published_at=now,
        fetched_at=now,
        raw={},
    )
    session.add(material)
    await session.flush()
    return material


async def test_event_clustering_eval_positive_negative_and_review(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        source = Source(name="Eval", feed_url="https://example.test/rss")
        session.add(source)
        await session.flush()
        first = await _material(session, source, "first", "Acme rocket launch confirmed in Europe")
        event = Event(source_material_id=first.id, cluster_key="same-key")
        session.add(event)
        await session.flush()
        session.add(EventMaterial(event_id=event.id, source_material_id=first.id))
        positive = await _material(
            session, source, "positive", "Acme confirms rocket launch in Europe"
        )
        merged = await decide_cluster(
            session, positive, event_key="same-key", entity_names=["Acme"]
        )
        assert merged.action == "auto_merge"
        assert merged.event_id == event.id
        assert merged.evidence["event_key_match"] is True
        negative = await _material(
            session, source, "negative", "City council approves a school budget"
        )
        separate = await decide_cluster(
            session, negative, event_key="different-key", entity_names=[]
        )
        assert separate.action == "separate"
        policy = await session.scalar(select(EventClusteringPolicy))
        assert policy is not None
        policy.auto_merge_threshold = 0.99
        policy.review_threshold = 0.01
        review = await decide_cluster(session, positive, event_key="different-key", entity_names=[])
        assert review.action == "review"


async def test_event_merge_and_split_preserve_all_materials(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        source = Source(name="Ops", feed_url="https://ops.test/rss")
        session.add(source)
        await session.flush()
        one, two, three = [
            await _material(session, source, key, f"Event {key}") for key in ("one", "two", "three")
        ]
        target = Event(source_material_id=one.id)
        source_event = Event(source_material_id=two.id)
        session.add_all([target, source_event])
        await session.flush()
        session.add_all(
            [
                EventMaterial(event_id=target.id, source_material_id=one.id),
                EventMaterial(event_id=source_event.id, source_material_id=two.id),
                EventMaterial(event_id=source_event.id, source_material_id=three.id),
            ]
        )
        await merge_events(
            session, target_event_id=target.id, source_event_id=source_event.id, actor_id="editor"
        )
        assert source_event.status == "merged"
        members = list(
            (
                await session.execute(
                    select(EventMaterial).where(EventMaterial.event_id == target.id)
                )
            ).scalars()
        )
        assert {member.source_material_id for member in members} == {one.id, two.id, three.id}
        operation = await session.scalar(select(EventClusterOperation).where(EventClusterOperation.operation == "merge"))
        assert operation is not None
        restored = await reverse_operation(session, operation_id=operation.id, actor_id="editor")
        assert restored.id == source_event.id
        assert source_event.status == "active"
        assert {member.source_material_id for member in (await session.execute(select(EventMaterial).where(EventMaterial.event_id == source_event.id))).scalars()} == {two.id, three.id}
        await merge_events(
            session, target_event_id=target.id, source_event_id=source_event.id, actor_id="editor"
        )
        split = await split_event(
            session, event_id=target.id, material_ids={three.id}, actor_id="editor"
        )
        assert split.status == "active"
        moved = list(
            (
                await session.execute(
                    select(EventMaterial).where(EventMaterial.event_id == split.id)
                )
            ).scalars()
        )
        assert [member.source_material_id for member in moved] == [three.id]
