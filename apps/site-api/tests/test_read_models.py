from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.main import create_app
from site_domain.models import (
    ArticleTranslationVersion,
    ArticleVersion,
    Publication,
    SiteArticle,
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
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    await engine.dispose()


async def test_public_read_model_supports_translation_and_taxonomy(
    client: httpx.AsyncClient,
) -> None:
    original = (await client.get("/api/v1/public/articles")).json()
    assert len(original) == 1
    assert original[0]["title"] == "Launch story"
    assert original[0]["available_languages"] == ["ar", "en"]
    translated = (await client.get("/api/v1/public/articles?language=ar")).json()
    assert translated[0]["title"] == "Arabic launch"
    assert translated[0]["direction"] == "rtl"
    categories = (await client.get("/api/v1/public/categories")).json()
    assert categories == [{"slug": "launches", "article_count": 1}]
    languages = (await client.get("/api/v1/public/languages")).json()
    assert {item["code"] for item in languages} == {"en", "ar"}


async def test_admin_read_model_requires_configured_token(client: httpx.AsyncClient) -> None:
    denied = await client.get("/api/v1/admin/articles")
    assert denied.status_code == 401
    allowed = await client.get(
        "/api/v1/admin/articles", headers={"X-Admin-Token": "test-admin-token"}
    )
    assert allowed.status_code == 200
    assert {item["status"] for item in allowed.json()} == {"published", "draft"}


async def test_unpublished_article_is_not_public(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/public/articles")
    assert response.status_code == 200
    assert len(response.json()) == 1
