from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.editorial import publish, review, submit_for_review
from site_api.errors import ConflictError
from site_domain.models import ArticleVersion, SiteArticle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def test_review_publish_and_unapproved_rejection(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        article = SiteArticle(status="draft", latest_version_number=1)
        session.add(article)
        await session.flush()
        session.add(
            ArticleVersion(
                article_id=article.id, version_number=1, content={}, created_by_actor_id="writer"
            )
        )
        article_id = article.id
    async with session_factory() as session:
        article = await submit_for_review(
            session, article_id=article_id, actor_id="writer", expected_lock_version=1
        )
    with pytest.raises(ConflictError):
        async with session_factory() as session:
            await review(
                session,
                article_id=article_id,
                actor_id="writer",
                expected_lock_version=article.lock_version,
                approve=True,
            )
    async with session_factory() as session:
        approved = await review(
            session,
            article_id=article_id,
            actor_id="editor",
            expected_lock_version=article.lock_version,
            approve=True,
        )
    async with session_factory() as session:
        published = await publish(
            session,
            article_id=article_id,
            actor_id="editor",
            expected_lock_version=approved.lock_version,
        )
    assert published.status == "published"
    async with session_factory() as session:
        version = (await session.execute(select(ArticleVersion))).scalar_one()
        assert version.version_number == 1


async def test_stale_optimistic_lock_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        article = SiteArticle(status="draft", latest_version_number=1)
        session.add(article)
        await session.flush()
        session.add(
            ArticleVersion(
                article_id=article.id, version_number=1, content={}, created_by_actor_id="writer"
            )
        )
        article_id = article.id
    async with session_factory() as session:
        await submit_for_review(
            session, article_id=article_id, actor_id="writer", expected_lock_version=1
        )
    with pytest.raises(ConflictError):
        async with session_factory() as session:
            await submit_for_review(
                session, article_id=article_id, actor_id="writer", expected_lock_version=1
            )
