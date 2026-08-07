from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.main import create_app
from site_api.media_generation import FakeImageProvider, MediaGateway
from site_api.storage import MemoryObjectStorage
from site_domain.models import ArticleVersion, Publication, SiteArticle
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("INSTANCE_ID", "22222222-2222-2222-2222-222222222222")
    monkeypatch.setenv("INSTANCE_TYPE", "site")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-token")
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = create_app()
    app.state.session_factory = create_session_factory(engine)
    app.state.object_storage = MemoryObjectStorage()
    app.state.media_gateway = MediaGateway([FakeImageProvider()])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    await engine.dispose()


async def _published_version(client: httpx.AsyncClient) -> str:
    app = client._transport.app  # type: ignore[attr-defined]
    async with app.state.session_factory() as session:
        article = SiteArticle(status="published", latest_version_number=1)
        session.add(article)
        await session.flush()
        version = ArticleVersion(
            article_id=article.id,
            version_number=1,
            created_by_actor_id="editor",
            content={"content": {"title": "Headline", "summary": "Summary", "language": "en"}},
        )
        session.add(version)
        await session.flush()
        session.add(
            Publication(
                article_id=article.id,
                active_article_version_id=version.id,
                status="published",
                published_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return str(version.id)


async def test_media_upload_generation_and_distribution_idempotency(
    client: httpx.AsyncClient,
) -> None:
    headers = {"X-Admin-Token": "test-token"}
    version_id = await _published_version(client)
    upload = await client.post(
        "/api/v1/admin/media",
        headers=headers,
        json={
            "content_base64": base64.b64encode(b"image").decode(),
            "mime_type": "image/png",
            "kind": "original",
            "rights": {"license": "owned"},
        },
    )
    assert upload.status_code == 201
    generated = await client.post(
        "/api/v1/admin/media/generate",
        headers=headers,
        json={"article_version_id": version_id, "variants": 2},
    )
    assert generated.status_code == 201
    assert len(generated.json()["assets"]) == 2
    channel = await client.post(
        "/api/v1/admin/distribution/channels",
        headers=headers,
        json={
            "name": "Telegram",
            "kind": "telegram",
            "account_key": "main",
            "credential_ref": "TEST",
            "config": {"chat_id": "@news"},
        },
    )
    assert channel.status_code == 201
    body = {"channel_id": channel.json()["id"], "article_version_id": version_id}
    first = await client.post("/api/v1/admin/distribution/jobs", headers=headers, json=body)
    second = await client.post("/api/v1/admin/distribution/jobs", headers=headers, json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["id"] == second.json()["id"]


async def test_media_and_distribution_negative_validation(client: httpx.AsyncClient) -> None:
    headers = {"X-Admin-Token": "test-token"}
    invalid_media = await client.post(
        "/api/v1/admin/media",
        headers=headers,
        json={"content_base64": "not-base64", "mime_type": "image/png"},
    )
    assert invalid_media.status_code == 422
    invalid_channel = await client.post(
        "/api/v1/admin/distribution/channels",
        headers=headers,
        json={"name": "Bad", "kind": "telegram", "account_key": "bad", "config": {}},
    )
    assert invalid_channel.status_code == 422
    leaked_secret = await client.post(
        "/api/v1/admin/distribution/channels",
        headers=headers,
        json={
            "name": "Unsafe",
            "kind": "telegram",
            "account_key": "unsafe",
            "config": {"chat_id": "1", "bot_token": "must-not-be-stored"},
        },
    )
    assert leaked_secret.status_code == 422
    assert "must-not-be-stored" not in leaked_secret.text
    valid = await client.post(
        "/api/v1/admin/distribution/channels",
        headers=headers,
        json={
            "name": "Safe",
            "kind": "telegram",
            "account_key": "safe",
            "config": {"chat_id": "1"},
        },
    )
    unsupported_update = await client.put(
        f"/api/v1/admin/distribution/channels/{valid.json()['id']}",
        headers=headers,
        json={
            "name": "Unsafe kind",
            "kind": "arbitrary-provider",
            "account_key": "safe",
            "config": {},
        },
    )
    assert unsupported_update.status_code == 422
