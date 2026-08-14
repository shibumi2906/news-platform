"""Transactional Site editorial workflow for Stage 1B."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from common.logging import get_logger
from common.time import utc_now
from site_domain.models import (
    ArticleSourceLink,
    ArticleTranslationVersion,
    ArticleVersion,
    ArticleVersionEntity,
    CorrectionNotice,
    EditorialTask,
    IncomingPackage,
    IncomingPackageVersion,
    Publication,
    ReviewDecision,
    SiteArticle,
    SiteEntity,
    SiteEvent,
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

from site_api.dashboard import enqueue_metric
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
    event = await _event_for_package(session, package_version.payload)
    version = ArticleVersion(
        article_id=article.id,
        version_number=1,
        content=package_version.payload,
        created_by_actor_id=actor_id,
        based_on_incoming_package_version_id=package_version.id,
        event_id=event.id,
    )
    session.add(version)
    await session.flush()
    await _link_package_entities(session, version.id, package_version.payload)
    original_content = package_version.payload.get("content", {})
    source_language = str(original_content.get("language", "und"))
    for language_code, translated_content in package_version.payload.get(
        "language_versions", {}
    ).items():
        session.add(
            ArticleTranslationVersion(
                article_version_id=version.id,
                source_language_code=source_language,
                language_code=language_code,
                direction=str(translated_content.get("direction", "ltr")),
                content=translated_content,
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
    previous_event_id = (
        await session.execute(
            select(ArticleVersion.event_id)
            .where(ArticleVersion.article_id == article.id)
            .order_by(ArticleVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    version = ArticleVersion(
        article_id=article.id,
        version_number=article.latest_version_number,
        content=content,
        created_by_actor_id=actor_id,
        event_id=previous_event_id,
    )
    session.add(version)
    await session.flush()
    await _copy_entity_links(session, article.id, version.id)
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


async def _event_for_package(session: AsyncSession, payload: dict[str, object]) -> SiteEvent:
    raw_event_id = payload.get("event_id")
    try:
        event_id = UUID(str(raw_event_id))
    except (TypeError, ValueError) as exc:
        raise ValidationDomainError("incoming package has invalid event_id") from exc
    event = (
        await session.execute(select(SiteEvent).where(SiteEvent.source_event_id == event_id))
    ).scalar_one_or_none()
    if event is not None:
        return event
    content = payload.get("content")
    content = content if isinstance(content, dict) else {}
    title = content.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValidationDomainError("incoming package has no event title")
    taxonomy = payload.get("taxonomy")
    event = SiteEvent(
        source_event_id=event_id,
        title=title.strip(),
        summary=content.get("summary") if isinstance(content.get("summary"), str) else None,
        taxonomy=[value for value in taxonomy if isinstance(value, str)]
        if isinstance(taxonomy, list)
        else [],
    )
    session.add(event)
    await session.flush()
    return event


async def _link_package_entities(
    session: AsyncSession, article_version_id: UUID, payload: dict[str, object]
) -> None:
    raw_entities = payload.get("entities")
    if not isinstance(raw_entities, list):
        return
    entity_ids: set[UUID] = set()
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            continue
        name, kind = raw_entity.get("name"), raw_entity.get("kind")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(kind, str)
            or not kind.strip()
        ):
            continue
        normalized_name = name.strip().casefold()
        entity = (
            await session.execute(
                select(SiteEntity).where(
                    SiteEntity.kind == kind.strip(),
                    SiteEntity.normalized_name == normalized_name,
                )
            )
        ).scalar_one_or_none()
        if entity is None:
            entity = SiteEntity(
                name=name.strip(), normalized_name=normalized_name, kind=kind.strip()
            )
            session.add(entity)
            await session.flush()
        entity_ids.add(entity.id)
    session.add_all(
        [
            ArticleVersionEntity(article_version_id=article_version_id, entity_id=entity_id)
            for entity_id in entity_ids
        ]
    )


async def _copy_entity_links(
    session: AsyncSession, article_id: UUID, new_version_id: UUID
) -> None:
    previous_version_id = (
        await session.execute(
            select(ArticleVersion.id)
            .where(ArticleVersion.article_id == article_id, ArticleVersion.id != new_version_id)
            .order_by(ArticleVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if previous_version_id is None:
        return
    entity_ids = list(
        (
            await session.execute(
                select(ArticleVersionEntity.entity_id).where(
                    ArticleVersionEntity.article_version_id == previous_version_id
                )
            )
        ).scalars()
    )
    session.add_all(
        [
            ArticleVersionEntity(article_version_id=new_version_id, entity_id=entity_id)
            for entity_id in entity_ids
        ]
    )


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
    await enqueue_metric(
        session,
        event_type="article.published",
        metric="articles_published",
        occurred_at=publication.published_at,
        idempotency_key=f"article_published:{publication.id}:{version.id}",
    )
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
