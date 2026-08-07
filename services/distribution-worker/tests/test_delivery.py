from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from common.db import Base, create_engine, create_session_factory
from distribution_worker.adapters import DeliveryResult, DistributionError
from distribution_worker.delivery import process_due_jobs
from site_domain.models import ArticleVersion, DistributionChannel, DistributionJob, SiteArticle
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class Adapter:
    kind = "telegram"

    def __init__(self, errors: int = 0) -> None:
        self.errors = errors
        self.calls = 0

    async def publish(self, **kwargs: object) -> DeliveryResult:
        self.calls += 1
        if self.calls <= self.errors:
            raise DistributionError("temporary", retryable=True)
        return DeliveryResult(external_id="external-1")


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


async def _job(factory: async_sessionmaker[AsyncSession], max_attempts: int = 3) -> DistributionJob:
    async with factory() as session:
        article = SiteArticle(status="published", latest_version_number=1)
        channel = DistributionChannel(
            name="Telegram",
            kind="telegram",
            account_key="news",
            config={"chat_id": "1"},
            credential_ref="TEST",
        )
        session.add_all([article, channel])
        await session.flush()
        version = ArticleVersion(
            article_id=article.id,
            version_number=1,
            content={},
            created_by_actor_id="editor",
        )
        session.add(version)
        await session.flush()
        now = datetime.now(UTC)
        job = DistributionJob(
            channel_id=channel.id,
            article_version_id=version.id,
            idempotency_key=f"key-{max_attempts}",
            status="scheduled",
            scheduled_at=now,
            next_attempt_at=now,
            max_attempts=max_attempts,
            payload={"title": "Headline"},
        )
        session.add(job)
        await session.commit()
        return job


async def test_delivery_success_is_audited(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    job = await _job(session_factory)
    stats = await process_due_jobs(
        session_factory, {"telegram": Adapter()}, batch_size=5, retry_base_seconds=0
    )
    async with session_factory() as session:
        current = await session.get(DistributionJob, job.id)
    assert stats["delivered"] == 1
    assert current is not None and current.status == "delivered"
    assert current.external_publication_id == "external-1"


async def test_retry_exhaustion_moves_job_to_dlq(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    job = await _job(session_factory, max_attempts=1)
    stats = await process_due_jobs(
        session_factory, {"telegram": Adapter(errors=1)}, batch_size=5, retry_base_seconds=0
    )
    async with session_factory() as session:
        current = await session.get(DistributionJob, job.id)
    assert stats["dlq"] == 1
    assert current is not None and current.status == "dlq"
    assert current.error_message is not None and "Headline" not in current.error_message
