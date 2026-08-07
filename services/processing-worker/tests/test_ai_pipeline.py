from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_domain.models import (
    AIOperationRun,
    CanonicalNewsPackage,
    DraftProvenance,
    Event,
    EventMaterial,
    MaterialRelevance,
    OutboxEvent,
    PromptTemplate,
    PromptVersion,
    Source,
    SourceMaterial,
    Topic,
)
from processing_worker.ai_gateway import AIGateway, FakeAIProvider
from processing_worker.processing import process_pending_events
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _seed_configuration(
    factory: async_sessionmaker[AsyncSession], *, exclusions: list[str] | None = None
) -> uuid.UUID:
    async with factory() as session, session.begin():
        topic = Topic(
            name="Space",
            slug="space",
            keywords=["acme", "rocket"],
            exclusions=exclusions or [],
            categories=[{"name": "Launch", "slug": "launch", "keywords": ["rocket"]}],
        )
        session.add(topic)
        await session.flush()
        for operation, schema in (
            ("relevance", "RelevanceOutput"),
            ("extraction", "ExtractionOutput"),
            ("draft", "DraftOutput"),
        ):
            template = PromptTemplate(operation=operation)
            session.add(template)
            await session.flush()
            session.add(
                PromptVersion(
                    template_id=template.id,
                    version=1,
                    system_prompt=f"{operation} system",
                    user_prompt=f"{operation} input",
                    output_schema=schema,
                    is_active=True,
                )
            )
        return topic.id


async def _seed_material(
    factory: async_sessionmaker[AsyncSession], source_name: str, external_id: str, title: str
) -> uuid.UUID:
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with factory() as session, session.begin():
        source = Source(name=source_name, feed_url=f"https://{external_id}.test/rss")
        session.add(source)
        await session.flush()
        material = SourceMaterial(
            source_id=source.id,
            external_id=external_id,
            url=f"https://{external_id}.test/story",
            canonical_url=f"https://{external_id}.test/story",
            canonical_url_hash=external_id,
            title=title,
            body="Acme confirmed the rocket launch on 2026-08-07.",
            language="en",
            published_at=now,
            fetched_at=now,
            raw={},
        )
        session.add(material)
        await session.flush()
        event = Event(source_material_id=material.id)
        session.add(event)
        await session.flush()
        session.add(
            OutboxEvent(
                event_type="source_material.ingested",
                payload={"source_material_id": str(material.id), "event_id": str(event.id)},
            )
        )
        return material.id


def _gateway() -> AIGateway:
    extraction = {
        "facts": [
            {
                "statement": "Acme launched a rocket.",
                "fact_type": "launch",
                "value": {"organization": "Acme"},
                "confidence": 0.9,
            }
        ],
        "entities": [
            {"kind": "organization", "name": "Acme", "confidence": 0.95},
            {"kind": "place", "name": "Europe", "confidence": 0.8},
            {"kind": "date", "name": "2026-08-07", "confidence": 1.0},
        ],
        "dates": ["2026-08-07"],
        "tags": ["space"],
        "event_key": "acme-rocket-2026-08-07",
    }
    return AIGateway([FakeAIProvider({"extraction": extraction})])


async def test_two_materials_cluster_into_versioned_draft_with_provenance(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_configuration(session_factory)
    await _seed_material(session_factory, "Wire A", "a", "Acme rocket launch")
    await _seed_material(session_factory, "Wire B", "b", "Rocket launched by Acme")

    stats = await process_pending_events(
        session_factory, instance_id=uuid.uuid4(), batch_size=10, gateway=_gateway()
    )
    assert stats.processed == 2

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(MaterialRelevance)) == 2
        assert await session.scalar(select(func.count()).select_from(EventMaterial)) == 2
        clustered_events = (
            (await session.execute(select(Event).where(Event.cluster_key.is_not(None))))
            .scalars()
            .all()
        )
        assert len(clustered_events) == 1
        packages = (
            (
                await session.execute(
                    select(CanonicalNewsPackage).order_by(CanonicalNewsPackage.package_version)
                )
            )
            .scalars()
            .all()
        )
        assert [item.package_version for item in packages] == [1, 2]
        assert packages[0].package_id == packages[1].package_id
        assert len(packages[1].sources) == 2
        assert packages[1].content["lead"]
        assert await session.scalar(select(func.count()).select_from(DraftProvenance)) == 3
        runs = (await session.execute(select(AIOperationRun))).scalars().all()
        assert len(runs) == 6
        assert all(run.provider == "fake" and run.model == "deterministic-v1" for run in runs)
        assert all(run.prompt_tokens > 0 for run in runs)


async def test_exclusion_rule_marks_material_irrelevant(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_configuration(session_factory, exclusions=["rumor"])
    await _seed_material(session_factory, "Wire", "excluded", "Acme rocket rumor")
    stats = await process_pending_events(
        session_factory, instance_id=uuid.uuid4(), batch_size=10, gateway=_gateway()
    )
    assert stats.irrelevant == 1
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(CanonicalNewsPackage)) == 0


async def test_invalid_ai_output_fails_without_losing_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_configuration(session_factory)
    material_id = await _seed_material(session_factory, "Wire", "bad", "Acme rocket")
    gateway = AIGateway([FakeAIProvider({"extraction": {"facts": []}})])
    stats = await process_pending_events(
        session_factory, instance_id=uuid.uuid4(), batch_size=10, gateway=gateway
    )
    assert stats.failed == 1
    async with session_factory() as session:
        material = await session.get(SourceMaterial, material_id)
        assert material is not None
        outbox = (await session.execute(select(OutboxEvent))).scalars().first()
        assert outbox is not None and outbox.status == "failed"
        failed_run = (
            await session.execute(select(AIOperationRun).where(AIOperationRun.status == "failed"))
        ).scalar_one()
        assert failed_run.operation == "extraction"
        assert failed_run.output is None
