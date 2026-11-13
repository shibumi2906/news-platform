"""Read models for monitoring automatic material selection."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from uuid import UUID

from common.auth import AuthContext, require_permission
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from integrator_domain.models import (
    CanonicalNewsPackage,
    IntegrationAuditEvent,
    MaterialRelevance,
    OutboxEvent,
    SiteConnection,
    Source,
    SourceMaterial,
    Topic,
)
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1/admin",
    dependencies=[Depends(require_permission("system:read"))],
)
delivery_manager = Depends(require_permission("jobs:manage"))


def topic_filter(session: AsyncSession, slug: str):
    package = CanonicalNewsPackage
    legacy_id = select(Topic.id).where(Topic.slug == slug).scalar_subquery()
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy import String, cast
        from sqlalchemy.dialects.postgresql import JSONB

        return or_(
            package.topics.cast(JSONB).contains([{"slug": slug}]),
            package.taxonomy.cast(JSONB).contains([slug]),
            package.taxonomy.cast(JSONB).contains(func.jsonb_build_array(cast(legacy_id, String))),
        )
    topics = func.json_each(package.topics).table_valued("value")
    taxonomy = func.json_each(package.taxonomy).table_valued("value")
    return or_(
        select(1)
        .select_from(topics)
        .where(func.json_extract(topics.c.value, "$.slug") == slug)
        .exists(),
        select(1)
        .select_from(taxonomy)
        .where(
            or_(
                taxonomy.c.value == slug,
                func.replace(taxonomy.c.value, "-", "") == legacy_id,
            )
        )
        .exists(),
    )


def source_filter(session: AsyncSession, source_id: UUID):
    package = CanonicalNewsPackage
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        return package.sources.cast(JSONB).contains([{"source_id": str(source_id)}])
    sources = func.json_each(package.sources).table_valued("value")
    return (
        select(1)
        .select_from(sources)
        .where(func.json_extract(sources.c.value, "$.source_id") == str(source_id))
        .exists()
    )


@router.get("/selected-materials")
async def selected_materials(
    request: Request,
    topic: str | None = Query(default=None, max_length=255),
    source: UUID | None = None,
    since: date | None = None,
    until: date | None = None,
    page: int = Query(default=1, ge=1, le=10000),
):
    package = CanonicalNewsPackage
    newer = package.__table__.alias("newer")
    query = select(package).where(
        ~select(1)
        .select_from(newer)
        .where(
            newer.c.package_id == package.package_id,
            newer.c.package_version > package.package_version,
        )
        .exists(),
        package.operation.not_in(["retracted", "deleted"]),
    )
    async with request.app.state.session_factory() as session:
        if topic:
            query = query.where(topic_filter(session, topic))
        if source:
            query = query.where(source_filter(session, source))
        if since:
            query = query.where(package.created_at >= datetime.combine(since, time.min, UTC))
        if until:
            query = query.where(package.created_at <= datetime.combine(until, time.max, UTC))
        rows = (
            await session.scalars(
                query.order_by(package.created_at.desc(), package.id.desc())
                .offset((page - 1) * 30)
                .limit(31)
            )
        ).all()
        material_ids = {
            UUID(ref["source_material_id"])
            for row in rows[:30]
            for ref in row.sources
            if ref.get("source_material_id")
        }
        matches = (
            await session.execute(
                select(MaterialRelevance, Topic.name)
                .join(Topic, Topic.id == MaterialRelevance.topic_id)
                .where(
                    MaterialRelevance.source_material_id.in_(material_ids),
                    MaterialRelevance.is_relevant,
                )
            )
        ).all()
        reasons = {}
        for match, name in matches:
            reasons.setdefault(str(match.source_material_id), []).append(
                {"topic": name, "reason": match.reason}
            )
        return {
            "items": [
                {
                    "id": row.id,
                    "content": row.content,
                    "created_at": row.created_at,
                    "topics": row.topics,
                    "categories": row.categories,
                    "sources": row.sources,
                    "taxonomy": row.taxonomy,
                    "reasons": [
                        item
                        for ref in row.sources
                        for item in reasons.get(ref.get("source_material_id"), [])
                    ],
                }
                for row in rows[:30]
            ],
            "has_more": len(rows) > 30,
        }


@router.get("/selection-history")
async def selection_history(
    request: Request,
    page: int = Query(default=1, ge=1, le=10000),
    errors_only: bool = False,
):
    query = select(SourceMaterial, Source.name).join(Source, Source.id == SourceMaterial.source_id)
    if errors_only:
        from sqlalchemy import String, cast

        query = query.where(
            select(1)
            .where(
                OutboxEvent.event_type == "source_material.ingested",
                OutboxEvent.status == "failed",
                func.replace(OutboxEvent.payload["source_material_id"].as_string(), "-", "")
                == func.replace(cast(SourceMaterial.id, String), "-", ""),
            )
            .exists()
        )
    async with request.app.state.session_factory() as session:
        rows = (
            await session.execute(
                query.order_by(SourceMaterial.fetched_at.desc(), SourceMaterial.id.desc())
                .offset((page - 1) * 30)
                .limit(31)
            )
        ).all()
        ids = [material.id for material, _ in rows[:30]]
        matches = (
            await session.execute(
                select(MaterialRelevance, Topic.name)
                .join(Topic, Topic.id == MaterialRelevance.topic_id)
                .where(MaterialRelevance.source_material_id.in_(ids))
            )
        ).all()
        events = (
            await session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.event_type == "source_material.ingested",
                    OutboxEvent.payload["source_material_id"].as_string().in_(map(str, ids)),
                )
                .order_by(OutboxEvent.created_at)
            )
        ).all()
        decisions = {}
        for match, topic in matches:
            decisions.setdefault(match.source_material_id, []).append(
                {
                    "topic": topic,
                    "passed": match.is_relevant,
                    "reason": match.reason,
                }
            )
        status = {
            event.payload["source_material_id"]: (
                event.status,
                event.payload.get("processing_error"),
            )
            for event in events
        }
        return {
            "items": [
                {
                    "id": material.id,
                    "title": material.title,
                    "url": material.url,
                    "source": name,
                    "status": status.get(str(material.id), ("pending", None))[0],
                    "error": status.get(str(material.id), ("pending", None))[1],
                    "decisions": decisions.get(material.id, []),
                }
                for material, name in rows[:30]
            ],
            "has_more": len(rows) > 30,
        }


@router.get("/selection-overview")
async def selection_overview(request: Request):
    from common.time import utc_now

    async with request.app.state.session_factory() as session:
        recent = await session.scalar(
            select(func.count())
            .select_from(CanonicalNewsPackage)
            .where(
                CanonicalNewsPackage.created_at >= utc_now() - timedelta(days=1),
                CanonicalNewsPackage.operation == "created",
            )
        )
        sources = await session.scalar(
            select(func.count())
            .select_from(Source)
            .where(
                Source.health_status != "healthy",
            )
        )
        failures = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(
                OutboxEvent.event_type == "source_material.ingested",
                OutboxEvent.status == "failed",
                OutboxEvent.payload["source_material_id"].as_string().is_not(None),
            )
        )
        return {"selected": recent, "source_errors": sources, "processing_errors": failures}


@router.get("/selection-filters")
async def selection_filters(request: Request):
    async with request.app.state.session_factory() as session:
        topics = (await session.execute(select(Topic.slug, Topic.name).order_by(Topic.name))).all()
        sources = (
            await session.execute(select(Source.id, Source.name).order_by(Source.name))
        ).all()
        return {
            "topics": [{"slug": slug, "name": name} for slug, name in topics],
            "sources": [{"id": source_id, "name": name} for source_id, name in sources],
        }


@router.get("/site-feed-activity")
async def feed_activity(request: Request):
    async with request.app.state.session_factory() as session:
        rows = (await session.scalars(select(SiteConnection).order_by(SiteConnection.name))).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "active": row.is_active,
                "last_pull_at": row.last_pull_at,
                "delivery_mode": row.delivery_mode,
            }
            for row in rows
        ]


class DeliveryMode(BaseModel):
    mode: Literal["push", "pull"]


@router.put("/site-feed-activity/{connection_id}")
async def change_delivery_mode(
    connection_id: UUID,
    payload: DeliveryMode,
    request: Request,
    actor: AuthContext = delivery_manager,
):
    async with request.app.state.session_factory() as session, session.begin():
        site = await session.get(SiteConnection, connection_id, with_for_update=True)
        if site is None:
            raise HTTPException(404, "Connection not found")
        if site.delivery_mode != payload.mode:
            site.delivery_mode = payload.mode
            session.add(
                IntegrationAuditEvent(
                    actor=actor.actor,
                    action="connection.delivery_mode_changed",
                    resource_type="site_connection",
                    resource_id=str(site.id),
                    details={"mode": payload.mode},
                )
            )
    return {"mode": payload.mode}
