from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from integrator_api.main import create_app
from integrator_domain.models import (
    CanonicalNewsPackage,
    Delivery,
    Event,
    IntegrationAuditEvent,
    OutboxEvent,
    ReplayRequest,
    SiteConnection,
    Source,
    SourceMaterial,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def client_and_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]]]:
    monkeypatch.setenv("INSTANCE_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("INSTANCE_TYPE", "integrator")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ADMIN_API_TOKEN", "integration-admin-token")
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    app = create_app()
    app.state.session_factory = factory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://integrator",
        headers={"X-Admin-Token": "integration-admin-token"},
    ) as client:
        yield client, factory
    await engine.dispose()


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[CanonicalNewsPackage, SiteConnection]:
    now = datetime(2026, 8, 26, 10, tzinfo=UTC)
    async with factory() as session, session.begin():
        source = Source(name="Wire", feed_url="https://wire.test/rss")
        session.add(source)
        await session.flush()
        material = SourceMaterial(
            source_id=source.id,
            external_id="one",
            url="https://wire.test/one",
            canonical_url="https://wire.test/one",
            canonical_url_hash="one",
            title="Original",
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
        package = CanonicalNewsPackage(
            package_version=1,
            instance_id=uuid.uuid4(),
            event_id=event.id,
            operation="created",
            content={
                "title": "Original",
                "canonical_url": material.canonical_url,
                "language": "en",
            },
            sources=[
                {
                    "source_id": str(source.id),
                    "source_material_id": str(material.id),
                    "external_id": material.external_id,
                    "url": material.url,
                    "published_at": now.isoformat(),
                    "fetched_at": now.isoformat(),
                }
            ],
        )
        connection = SiteConnection(
            name="Entertainment",
            delivery_url="https://entertainment.test",
            hmac_secret="old-secret-value",
        )
        session.add_all([package, connection])
        await session.flush()
        return package, connection


async def test_create_correct_retract_delete_are_immutable_versions(
    client_and_factory: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = client_and_factory
    package, _ = await _seed(factory)
    correction = await client.post(
        f"/api/v1/admin/integration/packages/{package.package_id}/revisions",
        json={
            "operation": "corrected",
            "reason": "Name corrected",
            "content": {
                "title": "Corrected",
                "canonical_url": "https://wire.test/one",
                "language": "en",
            },
        },
    )
    assert correction.status_code == 201
    for operation in ("retracted", "deleted"):
        response = await client.post(
            f"/api/v1/admin/integration/packages/{package.package_id}/revisions",
            json={"operation": operation, "reason": f"{operation} by source"},
        )
        assert response.status_code == 201

    async with factory() as session:
        versions = list(
            (
                await session.execute(
                    select(CanonicalNewsPackage)
                    .where(CanonicalNewsPackage.package_id == package.package_id)
                    .order_by(CanonicalNewsPackage.package_version)
                )
            ).scalars()
        )
        assert [item.operation for item in versions] == [
            "created",
            "corrected",
            "retracted",
            "deleted",
        ]
        assert [item.package_version for item in versions] == [1, 2, 3, 4]
        assert versions[0].content["title"] == "Original"
        assert versions[1].content["title"] == "Corrected"
        assert await session.scalar(select(func.count()).select_from(IntegrationAuditEvent)) == 3


async def test_replay_is_scoped_and_idempotent(
    client_and_factory: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = client_and_factory
    package, connection = await _seed(factory)
    payload = {"connection_id": str(connection.id), "package_id": str(package.package_id)}
    unauthorized = await client.post(
        "/api/v1/admin/integration/replays",
        headers={"X-Admin-Token": "", "Idempotency-Key": "unauthorized"},
        json=payload,
    )
    assert unauthorized.status_code == 401
    first = await client.post(
        "/api/v1/admin/integration/replays",
        headers={"Idempotency-Key": "backfill-one"},
        json=payload,
    )
    second = await client.post(
        "/api/v1/admin/integration/replays",
        headers={"Idempotency-Key": "backfill-one"},
        json=payload,
    )
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert first.json()["package_count"] == 1
    status = await client.get(f"/api/v1/admin/integration/replays/{first.json()['id']}")
    assert status.status_code == 200
    assert status.json() == first.json()
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ReplayRequest)) == 1
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        assert await session.scalar(select(func.count()).select_from(CanonicalNewsPackage)) == 1


async def test_dead_letter_visibility_manual_retry_and_key_rotation_do_not_expose_secrets(
    client_and_factory: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = client_and_factory
    package, connection = await _seed(factory)
    async with factory() as session, session.begin():
        delivery = Delivery(
            package_id=package.package_id,
            package_version=1,
            connection_id=connection.id,
            idempotency_key=f"{package.package_id}:1",
            status="dead_lettered",
            attempt_budget_used=3,
            last_error="http_500",
            dead_lettered_at=datetime.now(UTC),
        )
        session.add(delivery)
        await session.flush()
        delivery_id = delivery.id

    listed = await client.get("/api/v1/admin/integration/deliveries/dead-letters")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == str(delivery_id)
    retried = await client.post(
        f"/api/v1/admin/integration/deliveries/{delivery_id}/retry"
    )
    assert retried.status_code == 202

    rotated = await client.put(
        f"/api/v1/admin/integration/connections/{connection.id}/signing-key",
        json={"key_id": "v2", "secret": "new-secret-value-long-enough"},
    )
    assert rotated.status_code == 200
    assert rotated.json()["active_key_id"] == "v2"
    assert "secret" not in rotated.text
    retired = await client.delete(
        f"/api/v1/admin/integration/connections/{connection.id}/previous-signing-key"
    )
    assert retired.status_code == 204

    async with factory() as session:
        stored = await session.get(Delivery, delivery_id)
        stored_connection = await session.get(SiteConnection, connection.id)
        assert stored is not None and stored.status == "pending"
        assert stored.attempt_budget_used == 0 and stored.manual_retry_count == 1
        assert stored_connection is not None
        assert stored_connection.previous_hmac_secret is None
        audits = list((await session.execute(select(IntegrationAuditEvent))).scalars())
        assert all("secret" not in str(item.details).lower() for item in audits)

async def test_pull_feed_filters_pages_and_records_activity(client_and_factory, monkeypatch):
    from common.signing import sign
    from common.time import utc_now
    from contracts.package import CanonicalNewsPackageEnvelope
    from integrator_api.api import site_feed
    import json

    class Nonces:
        seen = set()

        @classmethod
        def from_url(cls, *args, **kwargs):
            return cls()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def set(self, key, *args, **kwargs):
            if key in self.seen:
                return False
            self.seen.add(key)
            return True

    monkeypatch.setattr(site_feed, "Redis", Nonces)
    client, factory = client_and_factory
    package, connection = await _seed(factory)
    async with factory() as session, session.begin():
        row = await session.get(CanonicalNewsPackage, package.id)
        row.topics = [{"id": str(uuid.uuid4()), "slug": "texas-news"}]

    async def pull(topic, cursor=None, nonce=None, secret=connection.hmac_secret):
        body = json.dumps({"topic": topic, "cursor": cursor}).encode()
        timestamp = utc_now().isoformat()
        nonce = nonce or uuid.uuid4().hex
        return await client.post("/api/v1/site-feed/materials", content=body, headers={
            "Content-Type": "application/json",
            "X-Connection-Id": str(connection.id), "X-Timestamp": timestamp,
            "X-Nonce": nonce, "X-Signature": sign(
                secret, timestamp=timestamp, nonce=nonce,
                idempotency_key="site-feed/materials", body=body,
            ),
        })

    assert (await pull("texas-news")).status_code == 401
    mode = await client.put(f"/api/v1/admin/site-feed-activity/{connection.id}", json={"mode": "pull"})
    assert mode.status_code == 200
    assert (await pull("texas-news", secret="wrong")).status_code == 401
    assert (await pull("california-news")).json()["items"] == []
    nonce = uuid.uuid4().hex
    result = await pull("texas-news", nonce=nonce)
    assert result.status_code == 200, result.text
    item, = result.json()["items"]
    assert CanonicalNewsPackageEnvelope.model_validate(item).package_id == package.package_id
    assert (await pull("texas-news", nonce=nonce)).status_code == 409
    assert (await pull("texas-news", result.json()["cursor"])).json()["items"] == []
    activity = (await client.get("/api/v1/admin/site-feed-activity")).json()
    assert activity[0]["delivery_mode"] == "pull"
    assert activity[0]["last_pull_at"]
    selected = await client.get("/api/v1/admin/selected-materials", params={"topic": "texas-news"})
    assert selected.status_code == 200, selected.text
    assert selected.json()["items"][0]["id"] == str(package.id)


async def test_topic_update_copy_and_preview(client_and_factory, monkeypatch):
    client, _ = client_and_factory
    path = "/api/v1/ai/topics"
    monkeypatch.setenv("AI_PROVIDERS", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")
    prompt = await client.post("/api/v1/ai/prompts", json={
        "operation": "relevance", "system_prompt": "Classify.", "user_prompt": "Select.",
        "output_schema": "RelevanceOutput",
    })
    assert prompt.status_code == 201
    created = await client.post(path, json={"name": "World news", "slug": "world-news"})
    assert created.status_code == 201
    topic = created.json()
    updated = {
        **topic, "keywords": ["film"], "exclusions": ["combat"],
        "additional_rules": {"include_criteria": "Film releases", "exclude_criteria": "War"},
    }
    assert (await client.put(f"{path}/{topic['id']}", json=updated)).json()["id"] == topic["id"]
    copy = await client.post(path, json={**updated, "name": "Texas news", "slug": "texas-news", "regions": ["Texas"]})
    assert copy.status_code == 201
    assert copy.json()["id"] != topic["id"]
    result = await client.post("/api/v1/ai/relevance/preview", json={"text": "Texas film premiere"})
    assert result.status_code == 200, result.text
    assert all(item["is_relevant"] for item in result.json()["matches"])
    assert (await client.get("/api/v1/admin/selected-materials")).json()["items"] == []

    model_path = "/api/v1/ai/relevance/model"
    response = await client.put(model_path, json={"model": "gpt-6-luna"})
    assert response.status_code == 200, response.text
    assert (await client.get(model_path)).json()["model"] == "gpt-6-luna"
    assert (await client.post(f"{model_path}/rollback")).status_code == 200
    assert (await client.get(model_path)).json()["model"] == "deterministic-v1"


async def test_source_form_configures_youtube_and_previews_without_saving(client_and_factory, monkeypatch):
    from integrator_api.api import sources

    client, _ = client_and_factory
    path = "/api/v1/sources"
    payload = {"name": "Arts", "feed_url": "https://www.youtube.com/@arts/videos", "adapter_type": "youtube"}

    async def collect(_client, *, config, **kwargs):
        assert config["channel_url"] == "https://www.youtube.com/@arts"
        assert config["api_key_env"] == "YOUTUBE_API_KEY"
        return [], None

    monkeypatch.setattr(sources, "collect_youtube_source", collect)
    assert (await client.post(f"{path}/sample", json=payload)).json() == {"items": []}
    assert (await client.get(path)).json() == []
    created = await client.post(path, json=payload)
    assert created.status_code == 201
    changed = await client.put(f"{path}/{created.json()['id']}", json={
        **payload, "feed_url": "https://www.youtube.com/playlist?list=PLArts",
    })
    assert changed.status_code == 200
    assert changed.json()["config"]["playlist_id"] == "PLArts"
    assert "channel_url" not in changed.json()["config"]
