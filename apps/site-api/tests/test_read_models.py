from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.main import create_app
from site_domain.models import (
    ArticleTranslationVersion,
    ArticleVersion,
    Publication,
    SiteArticle,
    SiteEvent,
)
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("INSTANCE_ID", "22222222-2222-2222-2222-222222222222")
    monkeypatch.setenv("INSTANCE_TYPE", "site")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = create_app()
    factory = create_session_factory(engine)
    app.state.session_factory = factory
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with factory() as session, session.begin():
        event = SiteEvent(
            source_event_id=uuid4(),
            title="Launch event",
            summary="Event summary",
            taxonomy=["launches"],
        )
        session.add(event)
        await session.flush()
        article = SiteArticle(status="published", latest_version_number=1)
        session.add(article)
        await session.flush()
        version = ArticleVersion(
            article_id=article.id,
            version_number=1,
            created_by_actor_id="writer",
            content={
                "content": {
                    "title": "Launch story",
                    "lead": "A launch happened.",
                    "body": "Full launch report.",
                    "summary": "Launch summary.",
                    "tags": ["space"],
                    "language": "en",
                    "direction": "ltr",
                },
                "taxonomy": ["launches"],
                "facts": [{"statement": "Launch happened"}],
                "entities": [],
                "sources": [],
            },
            event_id=event.id,
        )
        session.add(version)
        await session.flush()
        session.add_all(
            [
                ArticleTranslationVersion(
                    article_version_id=version.id,
                    source_language_code="en",
                    language_code="ar",
                    direction="rtl",
                    content={
                        "title": "Arabic launch",
                        "lead": "Arabic lead",
                        "body": "Arabic body",
                        "summary": "Arabic summary",
                        "tags": ["space-ar"],
                    },
                ),
                Publication(
                    article_id=article.id,
                    active_article_version_id=version.id,
                    status="published",
                    published_at=now,
                ),
                SiteArticle(status="draft", latest_version_number=0),
            ]
        )
        article_two = SiteArticle(status="published", latest_version_number=1)
        session.add(article_two)
        await session.flush()
        version_two = ArticleVersion(
            article_id=article_two.id,
            version_number=1,
            created_by_actor_id="writer",
            content={
                "content": {
                    "title": "Sports report",
                    "summary": "Match summary.",
                    "body": "Full match report.",
                    "language": "en",
                    "direction": "ltr",
                },
                "taxonomy": ["sports"],
            },
            event_id=event.id,
        )
        session.add(version_two)
        await session.flush()
        session.add(
            Publication(
                article_id=article_two.id,
                active_article_version_id=version_two.id,
                status="published",
                published_at=now.replace(day=8),
            )
        )
        rejected = SiteArticle(status="rejected_as_irrelevant", latest_version_number=1)
        unpublished = SiteArticle(status="unpublished", latest_version_number=1)
        session.add_all([rejected, unpublished])
        await session.flush()
        rejected_version = ArticleVersion(
            article_id=rejected.id,
            version_number=1,
            created_by_actor_id="writer",
            content={"content": {"title": "Rejected", "language": "en"}},
        )
        unpublished_version = ArticleVersion(
            article_id=unpublished.id,
            version_number=1,
            created_by_actor_id="writer",
            content={"content": {"title": "Unpublished", "language": "en"}},
        )
        session.add_all([rejected_version, unpublished_version])
        await session.flush()
        session.add_all(
            [
                Publication(
                    article_id=rejected.id,
                    active_article_version_id=rejected_version.id,
                    status="published",
                    published_at=now,
                ),
                Publication(
                    article_id=unpublished.id,
                    active_article_version_id=unpublished_version.id,
                    status="unpublished",
                    published_at=now,
                ),
            ]
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    await engine.dispose()


async def test_public_read_model_supports_translation_and_taxonomy(
    client: httpx.AsyncClient,
) -> None:
    original = (await client.get("/api/v1/public/articles")).json()
    assert original["total"] == 2
    assert original["items"][1]["title"] == "Launch story"
    assert original["items"][1]["available_languages"] == ["ar", "en"]
    translated = (await client.get("/api/v1/public/articles?language=ar")).json()
    assert translated["total"] == 1
    assert translated["items"][0]["title"] == "Arabic launch"
    assert translated["items"][0]["direction"] == "rtl"
    categories = (await client.get("/api/v1/public/categories")).json()
    assert categories == [
        {"slug": "launches", "article_count": 1},
        {"slug": "sports", "article_count": 1},
    ]
    languages = (await client.get("/api/v1/public/languages")).json()
    assert {item["code"] for item in languages} == {"en", "ar"}


async def test_admin_read_model_requires_configured_token(client: httpx.AsyncClient) -> None:
    denied = await client.get("/api/v1/admin/articles")
    assert denied.status_code == 401
    allowed = await client.get(
        "/api/v1/admin/articles", headers={"X-Admin-Token": "test-admin-token"}
    )
    assert allowed.status_code == 200
    assert {item["status"] for item in allowed.json()} == {
        "published",
        "draft",
        "rejected_as_irrelevant",
        "unpublished",
    }


async def test_unpublished_article_is_not_public(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/public/articles")
    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test_public_read_model_search_filters_pagination_and_sorting(
    client: httpx.AsyncClient,
) -> None:
    searched = await client.get("/api/v1/public/articles?query=match&topic=sports")
    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert searched.json()["items"][0]["title"] == "Sports report"
    paged = await client.get("/api/v1/public/articles?page=2&page_size=1&sort=newest")
    assert paged.json()["total"] == 2
    assert paged.json()["items"][0]["title"] == "Launch story"
    date_filtered = await client.get("/api/v1/public/articles?from_date=2026-08-08T00:00:00Z")
    assert [item["title"] for item in date_filtered.json()["items"]] == ["Sports report"]


async def test_public_events_only_include_published_timeline_articles(
    client: httpx.AsyncClient,
) -> None:
    events = await client.get("/api/v1/public/events")
    assert events.status_code == 200
    assert events.json()[0]["title"] == "Launch event"
    assert events.json()[0]["article_count"] == 2
    event_id = events.json()[0]["id"]
    detail = await client.get(f"/api/v1/public/events/{event_id}?language=en")
    assert detail.status_code == 200
    assert [article["title"] for article in detail.json()["articles"]] == [
        "Launch story",
        "Sports report",
    ]
    assert (await client.get("/api/v1/public/events/not-a-uuid")).status_code == 422
