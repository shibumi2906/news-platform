"""Public and admin read models for the Site web applications."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from common.auth import require_permission
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from site_domain.models import (
    ArticleTranslationVersion,
    ArticleVersion,
    ArticleVersionEntity,
    EditorialTask,
    IncomingPackage,
    IncomingPackageVersion,
    Publication,
    ReviewDecision,
    SiteArticle,
    SiteEntity,
    SiteEvent,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

public_router = APIRouter(prefix="/api/v1/public", tags=["public"])
admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["site-admin"],
    dependencies=[Depends(require_permission("articles:read"))],
)


class PublicArticle(BaseModel):
    id: UUID
    article_version_id: UUID
    title: str
    lead: str | None = None
    body: str | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    taxonomy: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    language: str
    direction: str
    available_languages: list[str] = Field(default_factory=list)
    published_at: datetime
    updated_at: datetime
    facts: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)


class PublicLanguage(BaseModel):
    code: str
    direction: str


class PublicCategory(BaseModel):
    slug: str
    article_count: int


class PublicRegion(BaseModel):
    slug: str
    article_count: int


class PublicArticlePage(BaseModel):
    items: list[PublicArticle]
    page: int
    page_size: int
    total: int


class PublicEvent(BaseModel):
    id: UUID
    title: str
    summary: str | None = None
    taxonomy: list[str] = Field(default_factory=list)
    latest_published_at: datetime
    article_count: int
    available_languages: list[str] = Field(default_factory=list)


class PublicEventDetail(PublicEvent):
    articles: list[PublicArticle]


class PublicEntity(BaseModel):
    id: UUID
    name: str
    kind: str
    latest_published_at: datetime
    article_count: int
    available_languages: list[str] = Field(default_factory=list)


class PublicEntityDetail(PublicEntity):
    articles: list[PublicArticle]


class IncomingPackageSummary(BaseModel):
    id: UUID
    version_id: UUID
    package_id: UUID
    latest_version: int
    title: str
    language: str
    received_at: datetime


class AdminArticleSummary(BaseModel):
    id: UUID
    status: str
    lock_version: int
    latest_version_number: int
    four_eyes_required: bool
    created_at: datetime
    updated_at: datetime


class AdminArticleDetail(AdminArticleSummary):
    versions: list[dict[str, Any]]
    translations: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    reviews: list[dict[str, Any]]
    publication: dict[str, Any] | None


@public_router.get("/articles", response_model=PublicArticlePage)
async def list_public_articles(
    request: Request,
    query: str | None = Query(default=None, max_length=200),
    language: str | None = None,
    category: str | None = None,
    topic: str | None = None,
    region: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    sort: Literal["newest", "oldest"] = "newest",
) -> PublicArticlePage:
    async with request.app.state.session_factory() as session:
        articles = await _published_articles(session, language)
    category_term = category.casefold() if category else None
    topic_term = topic.casefold() if topic else None
    region_term = region.casefold() if region else None
    needle = query.casefold().strip() if query else None
    filtered = [
        article
        for article in articles
        if (language is None or article.language == language)
        and (
            category_term is None
            or category_term in {value.casefold() for value in article.taxonomy}
        )
        and (topic_term is None or topic_term in {value.casefold() for value in article.taxonomy})
        and (region_term is None or region_term in {value.casefold() for value in article.regions})
        and (from_date is None or _utc(article.published_at) >= _utc(from_date))
        and (to_date is None or _utc(article.published_at) <= _utc(to_date))
        and (
            needle is None
            or needle
            in " ".join(
                value
                for value in [
                    article.title,
                    article.lead or "",
                    article.summary or "",
                    article.body or "",
                    *article.tags,
                    *article.taxonomy,
                ]
            ).casefold()
        )
    ]
    filtered.sort(
        key=lambda article: (article.published_at, str(article.id)), reverse=sort == "newest"
    )
    total = len(filtered)
    start = (page - 1) * page_size
    return PublicArticlePage(
        items=filtered[start : start + page_size],
        page=page,
        page_size=page_size,
        total=total,
    )


@public_router.get("/articles/{article_id}", response_model=PublicArticle)
async def get_public_article(
    article_id: UUID, request: Request, language: str | None = None
) -> PublicArticle:
    async with request.app.state.session_factory() as session:
        row = (
            await session.execute(
                select(SiteArticle, Publication, ArticleVersion)
                .join(Publication, Publication.article_id == SiteArticle.id)
                .join(ArticleVersion, ArticleVersion.id == Publication.active_article_version_id)
                .where(
                    SiteArticle.id == article_id,
                    SiteArticle.status == "published",
                    Publication.status == "published",
                    Publication.published_at.is_not(None),
                )
            )
        ).one_or_none()
        if row is None:
            article = await session.get(SiteArticle, article_id)
            if article is not None and article.status == "unpublished":
                raise HTTPException(410, "article has been permanently unpublished")
            raise HTTPException(404, "published article not found")
        article, publication, version = row
        return await _public_article(session, article, publication, version, language)


@public_router.get("/events", response_model=list[PublicEvent])
async def list_public_events(request: Request, language: str | None = None) -> list[PublicEvent]:
    async with request.app.state.session_factory() as session:
        grouped = await _published_events(session, language)
    return sorted(
        (_event_summary(event, articles) for event, articles in grouped.values()),
        key=lambda event: event.latest_published_at,
        reverse=True,
    )


@public_router.get("/events/{event_id}", response_model=PublicEventDetail)
async def get_public_event(
    event_id: UUID, request: Request, language: str | None = None
) -> PublicEventDetail:
    async with request.app.state.session_factory() as session:
        grouped = await _published_events(session, language)
    group = grouped.get(event_id)
    if group is None:
        raise HTTPException(404, "published event not found")
    event, articles = group
    summary = _event_summary(event, articles)
    return PublicEventDetail(
        **summary.model_dump(),
        articles=sorted(articles, key=lambda article: article.published_at),
    )


@public_router.get("/entities", response_model=list[PublicEntity])
async def list_public_entities(request: Request, language: str | None = None) -> list[PublicEntity]:
    async with request.app.state.session_factory() as session:
        grouped = await _published_entities(session, language)
    return sorted(
        (_entity_summary(entity, articles) for entity, articles in grouped.values()),
        key=lambda entity: entity.latest_published_at,
        reverse=True,
    )


@public_router.get("/entities/{entity_id}", response_model=PublicEntityDetail)
async def get_public_entity(
    entity_id: UUID, request: Request, language: str | None = None
) -> PublicEntityDetail:
    async with request.app.state.session_factory() as session:
        grouped = await _published_entities(session, language)
    group = grouped.get(entity_id)
    if group is None:
        raise HTTPException(404, "published entity not found")
    entity, articles = group
    summary = _entity_summary(entity, articles)
    return PublicEntityDetail(
        **summary.model_dump(),
        articles=sorted(articles, key=lambda article: article.published_at),
    )


@public_router.get("/categories", response_model=list[PublicCategory])
async def list_public_categories(request: Request) -> list[PublicCategory]:
    async with request.app.state.session_factory() as session:
        articles = await _published_articles(session, None)
    counts: dict[str, int] = {}
    for article in articles:
        for slug in article.taxonomy:
            counts[slug] = counts.get(slug, 0) + 1
    return [
        PublicCategory(slug=slug, article_count=count) for slug, count in sorted(counts.items())
    ]


@public_router.get("/regions", response_model=list[PublicRegion])
async def list_public_regions(request: Request) -> list[PublicRegion]:
    async with request.app.state.session_factory() as session:
        articles = await _published_articles(session, None)
    counts: dict[str, int] = {}
    for article in articles:
        for slug in article.regions:
            counts[slug] = counts.get(slug, 0) + 1
    return [PublicRegion(slug=slug, article_count=count) for slug, count in sorted(counts.items())]


@public_router.get("/languages", response_model=list[PublicLanguage])
async def list_public_languages(request: Request) -> list[PublicLanguage]:
    async with request.app.state.session_factory() as session:
        articles = await _published_articles(session, None)
    directions: dict[str, str] = {}
    for article in articles:
        directions[article.language] = article.direction
        async with request.app.state.session_factory() as session:
            translations = (
                await session.execute(
                    select(ArticleTranslationVersion).where(
                        ArticleTranslationVersion.article_version_id == article.article_version_id
                    )
                )
            ).scalars()
            for translation in translations:
                directions[translation.language_code] = translation.direction
    return [
        PublicLanguage(code=code, direction=direction)
        for code, direction in sorted(directions.items())
    ]


@admin_router.get("/incoming-packages", response_model=list[IncomingPackageSummary])
async def list_incoming_packages(
    request: Request, limit: int = Query(default=50, ge=1, le=200)
) -> list[IncomingPackageSummary]:
    async with request.app.state.session_factory() as session:
        packages = list(
            (
                await session.execute(
                    select(IncomingPackage).order_by(IncomingPackage.updated_at.desc()).limit(limit)
                )
            ).scalars()
        )
        result: list[IncomingPackageSummary] = []
        for package in packages:
            version = (
                await session.execute(
                    select(IncomingPackageVersion).where(
                        IncomingPackageVersion.incoming_package_id == package.id,
                        IncomingPackageVersion.package_version == package.latest_version,
                    )
                )
            ).scalar_one()
            content = _original_content(version.payload)
            result.append(
                IncomingPackageSummary(
                    id=package.id,
                    version_id=version.id,
                    package_id=package.package_id,
                    latest_version=package.latest_version,
                    title=_text(content, "title", "Untitled package"),
                    language=_text(content, "language", "und"),
                    received_at=version.created_at,
                )
            )
        return result


@admin_router.get("/articles", response_model=list[AdminArticleSummary])
async def list_admin_articles(
    request: Request, limit: int = Query(default=100, ge=1, le=200)
) -> list[AdminArticleSummary]:
    async with request.app.state.session_factory() as session:
        articles = (
            await session.execute(
                select(SiteArticle).order_by(SiteArticle.updated_at.desc()).limit(limit)
            )
        ).scalars()
        return [_admin_summary(article) for article in articles]


@admin_router.get("/articles/{article_id}", response_model=AdminArticleDetail)
async def get_admin_article(article_id: UUID, request: Request) -> AdminArticleDetail:
    async with request.app.state.session_factory() as session:
        article = await session.get(SiteArticle, article_id)
        if article is None:
            raise HTTPException(404, "article not found")
        versions = list(
            (
                await session.execute(
                    select(ArticleVersion)
                    .where(ArticleVersion.article_id == article.id)
                    .order_by(ArticleVersion.version_number.desc())
                )
            ).scalars()
        )
        version_ids = [version.id for version in versions]
        translations = (
            list(
                (
                    await session.execute(
                        select(ArticleTranslationVersion).where(
                            ArticleTranslationVersion.article_version_id.in_(version_ids)
                        )
                    )
                ).scalars()
            )
            if version_ids
            else []
        )
        tasks = list(
            (
                await session.execute(
                    select(EditorialTask)
                    .where(EditorialTask.article_id == article.id)
                    .order_by(EditorialTask.created_at.desc())
                )
            ).scalars()
        )
        reviews = list(
            (
                await session.execute(
                    select(ReviewDecision)
                    .where(ReviewDecision.article_id == article.id)
                    .order_by(ReviewDecision.created_at.desc())
                )
            ).scalars()
        )
        publication = (
            await session.execute(select(Publication).where(Publication.article_id == article.id))
        ).scalar_one_or_none()
        summary = _admin_summary(article)
        return AdminArticleDetail(
            **summary.model_dump(),
            versions=[
                {
                    "id": str(version.id),
                    "version_number": version.version_number,
                    "content": version.content,
                    "created_by_actor_id": version.created_by_actor_id,
                    "created_at": version.created_at,
                }
                for version in versions
            ],
            translations=[
                {
                    "id": str(item.id),
                    "article_version_id": str(item.article_version_id),
                    "language_code": item.language_code,
                    "direction": item.direction,
                    "content": item.content,
                }
                for item in translations
            ],
            tasks=[
                {
                    "id": str(task.id),
                    "status": task.status,
                    "reason": task.reason,
                    "assigned_actor_id": task.assigned_actor_id,
                }
                for task in tasks
            ],
            reviews=[
                {
                    "id": str(review.id),
                    "article_version_id": str(review.article_version_id),
                    "decision": review.decision,
                    "reason": review.reason,
                    "reviewer_actor_id": review.reviewer_actor_id,
                }
                for review in reviews
            ],
            publication=(
                {
                    "status": publication.status,
                    "active_article_version_id": str(publication.active_article_version_id)
                    if publication.active_article_version_id
                    else None,
                    "scheduled_at": publication.scheduled_at,
                    "published_at": publication.published_at,
                    "unpublished_at": publication.unpublished_at,
                }
                if publication
                else None
            ),
        )


async def _public_article(
    session: AsyncSession,
    article: SiteArticle,
    publication: Publication,
    version: ArticleVersion,
    requested_language: str | None,
) -> PublicArticle:
    translations = list(
        (
            await session.execute(
                select(ArticleTranslationVersion).where(
                    ArticleTranslationVersion.article_version_id == version.id
                )
            )
        ).scalars()
    )
    payload = version.content
    original = _original_content(payload)
    original_language = _text(original, "language", "und")
    selected = next(
        (item for item in translations if item.language_code == requested_language), None
    )
    content = selected.content if selected else original
    language = selected.language_code if selected else original_language
    direction = selected.direction if selected else _text(original, "direction", "ltr")
    available = sorted({original_language, *(item.language_code for item in translations)})
    if publication.published_at is None:
        raise HTTPException(500, "published article has no publication timestamp")
    return PublicArticle(
        id=article.id,
        article_version_id=version.id,
        title=_text(content, "title", "Untitled article"),
        lead=_optional_text(content, "lead"),
        body=_optional_text(content, "body"),
        summary=_optional_text(content, "summary"),
        tags=_string_list(content.get("tags")),
        taxonomy=_string_list(payload.get("taxonomy")),
        regions=_string_list(payload.get("regions")),
        language=language,
        direction=direction,
        available_languages=available,
        published_at=publication.published_at,
        updated_at=version.updated_at,
        facts=_dict_list(payload.get("facts")),
        entities=_dict_list(payload.get("entities")),
        sources=_dict_list(payload.get("sources")),
    )


async def _published_articles(
    session: AsyncSession, requested_language: str | None
) -> list[PublicArticle]:
    """Return only the active version of currently published articles."""
    rows = (
        await session.execute(
            select(SiteArticle, Publication, ArticleVersion)
            .join(Publication, Publication.article_id == SiteArticle.id)
            .join(ArticleVersion, ArticleVersion.id == Publication.active_article_version_id)
            .where(
                SiteArticle.status == "published",
                Publication.status == "published",
                Publication.published_at.is_not(None),
            )
        )
    ).all()
    return [
        await _public_article(session, article, publication, version, requested_language)
        for article, publication, version in rows
    ]


async def _published_events(
    session: AsyncSession, language: str | None
) -> dict[UUID, tuple[SiteEvent, list[PublicArticle]]]:
    articles = await _published_articles(session, language)
    if language is not None:
        articles = [article for article in articles if article.language == language]
    version_ids = [article.article_version_id for article in articles]
    if not version_ids:
        return {}
    rows = (
        await session.execute(
            select(ArticleVersion.id, SiteEvent)
            .join(SiteEvent, SiteEvent.id == ArticleVersion.event_id)
            .where(ArticleVersion.id.in_(version_ids))
        )
    ).all()
    events_by_version = {version_id: event for version_id, event in rows}
    grouped: dict[UUID, tuple[SiteEvent, list[PublicArticle]]] = {}
    for article in articles:
        event = events_by_version.get(article.article_version_id)
        if event is None:
            continue
        grouped.setdefault(event.id, (event, []))[1].append(article)
    return grouped


def _event_summary(event: SiteEvent, articles: list[PublicArticle]) -> PublicEvent:
    return PublicEvent(
        id=event.id,
        title=event.title,
        summary=event.summary,
        taxonomy=list(event.taxonomy),
        latest_published_at=max(article.published_at for article in articles),
        article_count=len(articles),
        available_languages=sorted(
            {language for article in articles for language in article.available_languages}
        ),
    )


async def _published_entities(
    session: AsyncSession, language: str | None
) -> dict[UUID, tuple[SiteEntity, list[PublicArticle]]]:
    articles = await _published_articles(session, language)
    if language is not None:
        articles = [article for article in articles if article.language == language]
    version_ids = [article.article_version_id for article in articles]
    if not version_ids:
        return {}
    rows = (
        await session.execute(
            select(ArticleVersionEntity.article_version_id, SiteEntity)
            .join(SiteEntity, SiteEntity.id == ArticleVersionEntity.entity_id)
            .where(ArticleVersionEntity.article_version_id.in_(version_ids))
        )
    ).all()
    entities_by_version: dict[UUID, list[SiteEntity]] = {}
    for version_id, entity in rows:
        entities_by_version.setdefault(version_id, []).append(entity)
    grouped: dict[UUID, tuple[SiteEntity, list[PublicArticle]]] = {}
    for article in articles:
        for entity in entities_by_version.get(article.article_version_id, []):
            grouped.setdefault(entity.id, (entity, []))[1].append(article)
    return grouped


def _entity_summary(entity: SiteEntity, articles: list[PublicArticle]) -> PublicEntity:
    return PublicEntity(
        id=entity.id,
        name=entity.name,
        kind=entity.kind,
        latest_published_at=max(article.published_at for article in articles),
        article_count=len(articles),
        available_languages=sorted(
            {language for article in articles for language in article.available_languages}
        ),
    )


def _admin_summary(article: SiteArticle) -> AdminArticleSummary:
    return AdminArticleSummary(
        id=article.id,
        status=article.status,
        lock_version=article.lock_version,
        latest_version_number=article.latest_version_number,
        four_eyes_required=article.four_eyes_required,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


def _original_content(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("content")
    return nested if isinstance(nested, dict) else payload


def _text(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) and value else default


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _optional_text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None


def _string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _dict_list(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
