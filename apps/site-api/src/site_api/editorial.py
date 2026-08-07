"""Transactional Site editorial workflow for Stage 1B."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from common.logging import get_logger
from common.time import utc_now
from site_domain.models import (
    ArticleSourceLink,
    ArticleVersion,
    CorrectionNotice,
    EditorialTask,
    IncomingPackage,
    IncomingPackageVersion,
    Publication,
    ReviewDecision,
    SiteArticle,
)
from site_domain.workflow import (
    APPROVED,
    DRAFT,
    NEEDS_REVIEW,
    PUBLISHED,
    PUBLISHING,
    SCHEDULED,
    UNPUBLISHED,
    ensure_transition_allowed,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from site_api.errors import ConflictError, NotFoundError, ValidationDomainError

logger = get_logger(__name__)


async def create_article_from_package(
    session: AsyncSession, *, incoming_package_version_id: UUID, actor_id: str
) -> SiteArticle:
    package_version = await session.get(IncomingPackageVersion, incoming_package_version_id)
    if package_version is None:
        raise NotFoundError("incoming package version not found")
    incoming = await session.get(IncomingPackage, package_version.incoming_package_id)
    if incoming is None:
        raise NotFoundError("incoming package not found")
    article = SiteArticle(status=DRAFT, latest_version_number=1)
    session.add(article)
    await session.flush()
    session.add(
        ArticleVersion(
            article_id=article.id,
            version_number=1,
            content=package_version.payload,
            created_by_actor_id=actor_id,
            based_on_incoming_package_version_id=package_version.id,
        )
    )
    session.add(
        ArticleSourceLink(
            article_id=article.id,
            incoming_package_id=incoming.id,
            last_merged_package_version=package_version.package_version,
        )
    )
    session.add(EditorialTask(article_id=article.id, reason="new_package"))
    await session.commit()
    logger.info(
        "article_created_from_package",
        article_id=str(article.id),
        package_version_id=str(package_version.id),
    )
    return article


async def create_version(
    session: AsyncSession,
    *,
    article_id: UUID,
    content: dict[str, object],
    actor_id: str,
    expected_lock_version: int,
    correction_explanation: str | None = None,
) -> SiteArticle:
    article = await _article_for_update(session, article_id, expected_lock_version)
    if article.status not in {DRAFT, PUBLISHED, NEEDS_REVIEW}:
        raise ConflictError("article cannot be edited in its current status")
    if article.status == PUBLISHED:
        ensure_transition_allowed(PUBLISHED, "corrected")
        article.status = "corrected"
    article.latest_version_number += 1
    article.lock_version += 1
    version = ArticleVersion(
        article_id=article.id,
        version_number=article.latest_version_number,
        content=content,
        created_by_actor_id=actor_id,
    )
    session.add(version)
    await session.flush()
    if correction_explanation is not None:
        if not correction_explanation.strip():
            raise ValidationDomainError("correction explanation is required")
        session.add(
            CorrectionNotice(
                article_id=article.id,
                article_version_id=version.id,
                explanation=correction_explanation,
            )
        )
    await session.commit()
    logger.info(
        "article_version_created", article_id=str(article.id), version=version.version_number
    )
    return article


async def submit_for_review(
    session: AsyncSession, *, article_id: UUID, actor_id: str, expected_lock_version: int
) -> SiteArticle:
    article = await _article_for_update(session, article_id, expected_lock_version)
    ensure_transition_allowed(article.status, NEEDS_REVIEW)
    article.status, article.lock_version = NEEDS_REVIEW, article.lock_version + 1
    session.add(EditorialTask(article_id=article.id, assigned_actor_id=None, reason="review"))
    await session.commit()
    return article


async def review(
    session: AsyncSession,
    *,
    article_id: UUID,
    actor_id: str,
    expected_lock_version: int,
    approve: bool,
    reason: str | None = None,
) -> SiteArticle:
    article = await _article_for_update(session, article_id, expected_lock_version)
    if article.status != NEEDS_REVIEW:
        raise ConflictError("article is not awaiting review")
    version = (
        await session.execute(
            select(ArticleVersion)
            .where(ArticleVersion.article_id == article.id)
            .order_by(ArticleVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one()
    if approve and article.four_eyes_required and version.created_by_actor_id == actor_id:
        raise ConflictError("four-eyes review requires a different actor")
    decision = APPROVED if approve else "rejected"
    session.add(
        ReviewDecision(
            article_id=article.id,
            article_version_id=version.id,
            reviewer_actor_id=actor_id,
            decision=decision,
            reason=reason,
        )
    )
    target = APPROVED if approve else DRAFT
    ensure_transition_allowed(article.status, target)
    article.status, article.lock_version = target, article.lock_version + 1
    await session.commit()
    logger.info("article_reviewed", article_id=str(article.id), decision=decision)
    return article


async def publish(
    session: AsyncSession,
    *,
    article_id: UUID,
    actor_id: str,
    expected_lock_version: int,
    scheduled_at: datetime | None = None,
) -> SiteArticle:
    article = await _article_for_update(session, article_id, expected_lock_version)
    target = SCHEDULED if scheduled_at and scheduled_at > utc_now() else PUBLISHING
    ensure_transition_allowed(article.status, target)
    publication = (
        await session.execute(select(Publication).where(Publication.article_id == article.id))
    ).scalar_one_or_none()
    if publication is None:
        publication = Publication(article_id=article.id, status=target, scheduled_at=scheduled_at)
        session.add(publication)
    else:
        publication.status, publication.scheduled_at = target, scheduled_at
    article.status, article.lock_version = target, article.lock_version + 1
    if target == SCHEDULED:
        await session.commit()
        return article
    await session.flush()
    version = (
        await session.execute(
            select(ArticleVersion)
            .where(ArticleVersion.article_id == article.id)
            .order_by(ArticleVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one()
    ensure_transition_allowed(PUBLISHING, PUBLISHED)
    publication.status, publication.active_article_version_id, publication.published_at = (
        PUBLISHED,
        version.id,
        utc_now(),
    )
    article.status = PUBLISHED
    await session.commit()
    logger.info("article_published", article_id=str(article.id), version=version.version_number)
    return article


async def unpublish(
    session: AsyncSession, *, article_id: UUID, expected_lock_version: int
) -> SiteArticle:
    article = await _article_for_update(session, article_id, expected_lock_version)
    ensure_transition_allowed(article.status, UNPUBLISHED)
    publication = (
        await session.execute(select(Publication).where(Publication.article_id == article.id))
    ).scalar_one_or_none()
    if publication is None:
        raise ConflictError("article has no publication")
    article.status, article.lock_version = UNPUBLISHED, article.lock_version + 1
    publication.status, publication.unpublished_at = UNPUBLISHED, utc_now()
    await session.commit()
    logger.info("article_unpublished", article_id=str(article.id))
    return article


async def _article_for_update(
    session: AsyncSession, article_id: UUID, expected: int
) -> SiteArticle:
    article = await session.get(SiteArticle, article_id)
    if article is None:
        raise NotFoundError("article not found")
    if article.lock_version != expected:
        raise ConflictError("article has been modified")
    return article
