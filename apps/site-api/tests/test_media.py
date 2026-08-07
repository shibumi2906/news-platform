from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.media_generation import (
    FakeImageProvider,
    MediaGateway,
    MediaModerationError,
)
from site_api.media_service import (
    AssetInput,
    create_meme,
    create_video_project,
    generate_article_images,
    select_media,
    store_asset,
)
from site_api.storage import MemoryObjectStorage
from site_domain.models import ArticleVersion, MemeTemplate, SiteArticle
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _article_version(factory: async_sessionmaker[AsyncSession]) -> ArticleVersion:
    async with factory() as session:
        article = SiteArticle(status="draft", latest_version_number=1)
        session.add(article)
        await session.flush()
        version = ArticleVersion(
            article_id=article.id,
            version_number=1,
            created_by_actor_id="editor",
            content={"content": {"title": "Space launch", "summary": "A new mission."}},
        )
        session.add(version)
        await session.commit()
        return version


async def test_generation_retries_stores_variants_and_selects_one(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    version = await _article_version(session_factory)
    storage = MemoryObjectStorage()
    provider = FakeImageProvider(fail_times=1)
    gateway = MediaGateway([provider], attempts_per_provider=2)
    async with session_factory() as session:
        run, assets = await generate_article_images(
            session,
            storage,
            gateway,
            article_version_id=version.id,
            variants=3,
        )
        link = await select_media(
            session,
            asset_id=assets[1].id,
            article_version_id=version.id,
            translation_version_id=None,
            role="hero",
        )
    assert provider.calls == 2
    assert run.status == "succeeded"
    assert len(assets) == 3
    assert len(storage.objects) == 3
    assert link.selected is True


async def test_moderation_records_failure_without_storing_content(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    version = await _article_version(session_factory)
    storage = MemoryObjectStorage()
    gateway = MediaGateway([FakeImageProvider(moderated=True)])
    async with session_factory() as session:
        with pytest.raises(MediaModerationError):
            await generate_article_images(
                session,
                storage,
                gateway,
                article_version_id=version.id,
                variants=1,
            )
    assert storage.objects == {}


async def test_gateway_falls_back_to_next_provider() -> None:
    unavailable = FakeImageProvider(fail_times=5)
    fallback = FakeImageProvider()
    result = await MediaGateway([unavailable, fallback], attempts_per_provider=1).generate(
        "safe prompt", 1
    )
    assert unavailable.calls == fallback.calls == 1
    assert result.provider == "fake"


async def test_manual_and_ai_meme_versions_and_video_storyboard(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    version = await _article_version(session_factory)
    storage = MemoryObjectStorage()
    async with session_factory() as session:
        base = await store_asset(
            session,
            storage,
            AssetInput(
                data=b"base",
                mime_type="image/png",
                kind="original",
                rights={"license": "owned"},
            ),
        )
        template = MemeTemplate(name="Breaking", base_asset_id=base.id, layout={})
        session.add(template)
        await session.commit()
        manual = await create_meme(
            session,
            storage,
            template_id=template.id,
            article_version_id=version.id,
            mode="manual",
            caption="Manual caption",
        )
        generated = await create_meme(
            session,
            storage,
            template_id=template.id,
            article_version_id=version.id,
            mode="ai",
            caption=None,
        )
        video = await create_video_project(session, article_version_id=version.id)
    assert (manual.version_number, generated.version_number) == (1, 2)
    assert generated.provenance["source_article_version_id"] == str(version.id)
    assert video.status == "ready"
    assert len(video.storyboard) == 3


async def test_translation_link_must_match_source_version(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    version = await _article_version(session_factory)
    other = await _article_version(session_factory)
    storage = MemoryObjectStorage()
    async with session_factory() as session:
        asset = await store_asset(
            session,
            storage,
            AssetInput(data=b"x", mime_type="image/png", kind="original"),
        )
        from site_domain.models import ArticleTranslationVersion

        translation = ArticleTranslationVersion(
            article_version_id=other.id,
            source_language_code="en",
            language_code="ar",
            direction="rtl",
            content={"title": "translated"},
        )
        session.add(translation)
        await session.commit()
        with pytest.raises(ValueError, match="does not belong"):
            await select_media(
                session,
                asset_id=asset.id,
                article_version_id=version.id,
                translation_version_id=translation.id,
                role="hero",
            )
