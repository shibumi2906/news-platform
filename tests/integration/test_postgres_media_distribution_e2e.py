"""PostgreSQL + Alembic + MinIO Media/Distribution vertical slice."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest
from common.db import create_engine, create_session_factory
from distribution_worker.adapters import DeliveryResult
from distribution_worker.delivery import process_due_jobs
from site_api.distribution import create_channel, schedule_distribution
from site_api.media_generation import FakeImageProvider, MediaGateway
from site_api.media_service import (
    AssetInput,
    create_meme,
    create_video_project,
    generate_article_images,
    select_media,
    store_asset,
)
from site_api.storage import S3ObjectStorage
from site_domain.models import (
    ArticleTranslationVersion,
    ArticleVersion,
    DistributionAttempt,
    DistributionJob,
    MediaAsset,
    MediaGenerationRun,
    MemeTemplate,
    Publication,
    SiteArticle,
    VideoProject,
)
from sqlalchemy import func, select

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL") or not os.getenv("MINIO_TEST_URL"),
    reason="requires POSTGRES_TEST_URL and MINIO_TEST_URL",
)

ROOT = Path(__file__).resolve().parents[2]


class FakeTelegramAdapter:
    kind = "telegram"

    async def publish(self, **kwargs: object) -> DeliveryResult:
        return DeliveryResult(external_id="telegram-message-100")


async def _run() -> None:
    admin_url = os.environ["POSTGRES_TEST_URL"]
    database_name = f"media_distribution_{uuid.uuid4().hex}"
    admin = await asyncpg.connect(admin_url)
    engine = None
    storage = S3ObjectStorage(
        endpoint_url=os.environ["MINIO_TEST_URL"],
        access_key=os.getenv("MINIO_TEST_ACCESS_KEY", "change-me"),
        secret_key=os.getenv("MINIO_TEST_SECRET_KEY", "change-me"),
        bucket=f"media-e2e-{uuid.uuid4().hex}",
        region="us-east-1",
    )
    object_keys: list[str] = []
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        target_url = admin_url.rsplit("/", 1)[0] + f"/{database_name}"
        sqlalchemy_url = target_url.replace("postgresql://", "postgresql+asyncpg://")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "migrations/site/alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": sqlalchemy_url},
            check=True,
        )
        engine = create_engine(sqlalchemy_url)
        factory = create_session_factory(engine)
        async with factory() as session:
            article = SiteArticle(status="published", latest_version_number=1)
            session.add(article)
            await session.flush()
            version = ArticleVersion(
                article_id=article.id,
                version_number=1,
                created_by_actor_id="e2e-editor",
                content={
                    "content": {
                        "title": "Media E2E",
                        "summary": "PostgreSQL to MinIO to Telegram queue.",
                        "body": "Immutable publication body.",
                        "language": "en",
                    }
                },
            )
            session.add(version)
            await session.flush()
            translation = ArticleTranslationVersion(
                article_version_id=version.id,
                source_language_code="en",
                language_code="ar",
                direction="rtl",
                content={"title": "Arabic", "summary": "Summary", "body": "Body"},
            )
            session.add(translation)
            session.add(
                Publication(
                    article_id=article.id,
                    active_article_version_id=version.id,
                    status="published",
                    published_at=datetime.now(UTC),
                )
            )
            await session.commit()

            original = await store_asset(
                session,
                storage,
                AssetInput(
                    data=b"real-minio-original",
                    mime_type="image/png",
                    kind="original",
                    source_event_id=uuid.uuid4(),
                    provenance={"source": "e2e"},
                    rights={"license": "owned", "allowed_uses": ["editorial"]},
                ),
            )
            object_keys.append(original.object_key)
            fetched, mime_type = await storage.get(original.object_key)
            assert fetched == b"real-minio-original"
            assert mime_type == "image/png"

            run, variants = await generate_article_images(
                session,
                storage,
                MediaGateway([FakeImageProvider()]),
                article_version_id=version.id,
                variants=2,
            )
            object_keys.extend(item.object_key for item in variants)
            await select_media(
                session,
                asset_id=variants[0].id,
                article_version_id=version.id,
                translation_version_id=translation.id,
                role="social",
            )
            template = MemeTemplate(name="E2E meme", base_asset_id=original.id, layout={})
            session.add(template)
            await session.commit()
            meme = await create_meme(
                session,
                storage,
                template_id=template.id,
                article_version_id=version.id,
                mode="ai",
                caption=None,
            )
            meme_asset = await session.get(MediaAsset, meme.output_asset_id)
            assert meme_asset is not None
            object_keys.append(meme_asset.object_key)
            video = await create_video_project(session, article_version_id=version.id)
            channel = await create_channel(
                session,
                name="E2E Telegram",
                kind="telegram",
                account_key="e2e",
                credential_ref="E2E",
                config={"chat_id": "@e2e"},
            )
            first, created = await schedule_distribution(
                session,
                channel_id=channel.id,
                article_version_id=version.id,
                translation_version_id=translation.id,
                media_asset_id=variants[0].id,
                scheduled_at=None,
                idempotency_key="media-e2e-idempotency",
                max_attempts=3,
            )
            second, duplicate_created = await schedule_distribution(
                session,
                channel_id=channel.id,
                article_version_id=version.id,
                translation_version_id=translation.id,
                media_asset_id=variants[0].id,
                scheduled_at=None,
                idempotency_key="media-e2e-idempotency",
                max_attempts=3,
            )
            assert created is True and duplicate_created is False and first.id == second.id

        stats = await process_due_jobs(
            factory,
            {"telegram": FakeTelegramAdapter()},
            batch_size=10,
            retry_base_seconds=0,
        )
        assert stats == {"delivered": 1, "retrying": 0, "dlq": 0, "failed": 0}
        async with factory() as session:
            job = (await session.execute(select(DistributionJob))).scalar_one()
            assert job.status == "delivered"
            assert job.external_publication_id == "telegram-message-100"
            assert await session.scalar(select(func.count(DistributionAttempt.id))) == 1
            assert await session.scalar(select(func.count(MediaGenerationRun.id))) == 1
            assert await session.scalar(select(func.count(VideoProject.id))) == 1
            assert run.provider == "fake"
            assert video.provider == "fake"
    finally:
        for key in object_keys:
            await storage.delete(key)
        await storage.close()
        if engine is not None:
            await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


def test_postgres_media_distribution_with_real_minio_and_migrations() -> None:
    asyncio.run(_run())
