from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_domain.models import (
    AIOperationRun,
    LanguageConfig,
    MaterialLanguageDetection,
    PromptTemplate,
    PromptVersion,
    Source,
    SourceMaterial,
    TerminologyEntry,
)
from processing_worker.ai_gateway import AIGateway, FakeAIProvider
from processing_worker.schemas import DraftOutput
from processing_worker.translation import TranslationPipelineError, generate_translations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _seed(factory: async_sessionmaker[AsyncSession]) -> SourceMaterial:
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with factory() as session, session.begin():
        session.add_all(
            [
                LanguageConfig(
                    code="en", name="English", direction="ltr", translation_enabled=True
                ),
                LanguageConfig(
                    code="he", name="Hebrew", direction="rtl", translation_enabled=True
                ),
            ]
        )
        session.add(
            TerminologyEntry(
                source_language_code="en",
                target_language_code="he",
                source_term="Acme",
                target_term="אקמי",
            )
        )
        for operation, schema in (
            ("language_detection", "LanguageDetectionOutput"),
            ("translation", "TranslationOutput"),
        ):
            template = PromptTemplate(operation=operation)
            session.add(template)
            await session.flush()
            session.add(
                PromptVersion(
                    template_id=template.id,
                    version=1,
                    system_prompt=f"{operation} system",
                    user_prompt=f"{operation} user",
                    output_schema=schema,
                    is_active=True,
                )
            )
        source = Source(name="Wire", feed_url="https://wire.test/rss")
        session.add(source)
        await session.flush()
        material = SourceMaterial(
            source_id=source.id,
            external_id="translation-1",
            url="https://wire.test/story",
            canonical_url="https://wire.test/story",
            canonical_url_hash="translation-1",
            title="Acme launch",
            body="Acme launched a rocket.",
            language="en",
            published_at=now,
            fetched_at=now,
            raw={},
        )
        session.add(material)
        await session.flush()
        return material


async def test_translation_uses_glossary_and_records_detection_and_usage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    material = await _seed(session_factory)
    draft = DraftOutput(
        title="Acme launch",
        lead="Acme launched.",
        body="Acme launched a rocket.",
        summary="Acme launch summary.",
        tags=["Acme"],
    )
    bundle = await generate_translations(
        session_factory, material, draft, AIGateway([FakeAIProvider()])
    )
    assert bundle.source_language_code == "en"
    assert bundle.source_direction == "ltr"
    assert len(bundle.translations) == 1
    translated = bundle.translations[0]
    assert translated.target_language_code == "he"
    assert translated.direction == "rtl"
    assert "אקמי" in translated.content.title
    assert translated.terminology_revision != ""
    async with session_factory() as session:
        detection = (await session.execute(select(MaterialLanguageDetection))).scalar_one()
        assert detection.language_code == "en"
        runs = (await session.execute(select(AIOperationRun))).scalars().all()
        assert {run.operation for run in runs} == {"language_detection", "translation"}
        assert all(run.prompt_tokens > 0 for run in runs)


async def test_invalid_translation_is_persisted_as_failed_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    material = await _seed(session_factory)
    draft = DraftOutput(title="T", lead="L", body="B", summary="S", tags=[])
    provider = FakeAIProvider({"translation": {"title": "missing other fields"}})
    with pytest.raises(TranslationPipelineError):
        await generate_translations(session_factory, material, draft, AIGateway([provider]))
    recovered = await generate_translations(
        session_factory, material, draft, AIGateway([FakeAIProvider()])
    )
    assert len(recovered.translations) == 1
    async with session_factory() as session:
        failed = (
            await session.execute(select(AIOperationRun).where(AIOperationRun.status == "failed"))
        ).scalar_one()
        assert failed.operation == "translation"
        assert failed.output is None
        detections = (await session.execute(select(MaterialLanguageDetection))).scalars().all()
        assert len(detections) == 1


async def test_unconfigured_detected_language_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    material = await _seed(session_factory)
    draft = DraftOutput(title="T", lead="L", body="B", summary="S", tags=[])
    provider = FakeAIProvider(
        {"language_detection": {"language_code": "zz", "confidence": 0.99}}
    )
    with pytest.raises(TranslationPipelineError, match="not configured"):
        await generate_translations(session_factory, material, draft, AIGateway([provider]))
    async with session_factory() as session:
        assert await session.scalar(select(MaterialLanguageDetection.id)) is None
