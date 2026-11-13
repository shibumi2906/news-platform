"""Secured integration contract operations: revisions, replay, DLQ, and keys."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from common.auth import AuthContext, require_permission
from common.logging import get_logger
from common.observability import METRICS
from contracts.package import PackageContent
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from integrator_domain.models import (
    CanonicalNewsPackage,
    Delivery,
    IntegrationAuditEvent,
    OutboxEvent,
    ReplayRequest,
    SiteConnection,
)
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/admin/integration", tags=["integration-operations"])
logger = get_logger(__name__)
CANONICAL_PACKAGE_CREATED = "canonical_news_package.created"

JobsManager = Depends(require_permission("jobs:manage"))
ArticlesWriter = Depends(require_permission("articles:write"))


class RevisionInput(BaseModel):
    operation: Literal["corrected", "retracted", "deleted"]
    reason: str = Field(min_length=1, max_length=2000)
    content: PackageContent | None = None

    @model_validator(mode="after")
    def corrected_content_required(self) -> RevisionInput:
        if self.operation == "corrected" and self.content is None:
            raise ValueError("corrected revisions require replacement content")
        return self


class ReplayInput(BaseModel):
    connection_id: UUID
    from_time: datetime | None = None
    to_time: datetime | None = None
    package_id: UUID | None = None
    min_version: int | None = Field(default=None, ge=1)
    max_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_scope(self) -> ReplayInput:
        if self.package_id is None and self.from_time is None and self.to_time is None:
            raise ValueError("replay requires a package_id or time bound")
        if self.from_time and self.to_time and self.from_time > self.to_time:
            raise ValueError("from_time must not be after to_time")
        if self.min_version and self.max_version and self.min_version > self.max_version:
            raise ValueError("min_version must not exceed max_version")
        return self


class KeyRotationInput(BaseModel):
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    secret: str = Field(min_length=16, max_length=255)


def _rate_limit(request: Request, actor: str) -> None:
    if not request.app.state.integration_limiter.allow(actor):
        raise HTTPException(429, "integration operation rate limit exceeded")


@router.post("/packages/{package_id}/revisions", status_code=201)
async def create_revision(
    package_id: UUID,
    payload: RevisionInput,
    request: Request,
    context: AuthContext = ArticlesWriter,
) -> dict[str, object]:
    _rate_limit(request, context.actor)
    async with request.app.state.session_factory() as session, session.begin():
        latest = (
            await session.execute(
                select(CanonicalNewsPackage)
                .where(CanonicalNewsPackage.package_id == package_id)
                .order_by(CanonicalNewsPackage.package_version.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if latest is None:
            raise HTTPException(404, "package not found")
        row = CanonicalNewsPackage(
            package_id=latest.package_id,
            package_version=latest.package_version + 1,
            instance_id=latest.instance_id,
            event_id=latest.event_id,
            event_stage=latest.event_stage,
            operation=payload.operation,
            revision_reason=payload.reason,
            content=(
                payload.content.model_dump(mode="json") if payload.content else latest.content
            ),
            facts=latest.facts,
            entities=latest.entities,
            taxonomy=latest.taxonomy,
            regions=latest.regions,
            topics=latest.topics,
            categories=latest.categories,
            geographies=latest.geographies,
            sources=latest.sources,
            language_versions=latest.language_versions,
            media=latest.media,
            ai_provenance=latest.ai_provenance,
            rights=latest.rights,
            confidence=latest.confidence,
            warnings=latest.warnings,
        )
        session.add(row)
        await session.flush()
        session.add(
            OutboxEvent(
                event_type=CANONICAL_PACKAGE_CREATED,
                payload={
                    "package_id": str(row.package_id),
                    "package_version": row.package_version,
                    "event_id": str(row.event_id),
                    "instance_id": str(row.instance_id),
                },
            )
        )
        session.add(
            IntegrationAuditEvent(
                actor=context.actor,
                action=f"package.{payload.operation}",
                resource_type="canonical_news_package",
                resource_id=f"{row.package_id}:{row.package_version}",
                details={"reason": payload.reason},
            )
        )
    METRICS.increment("package_revision_total", operation=payload.operation)
    logger.info(
        "package_revision_created",
        package_id=str(package_id),
        package_version=row.package_version,
        operation=payload.operation,
        actor=context.actor,
    )
    return {
        "package_id": str(row.package_id),
        "package_version": row.package_version,
        "operation": row.operation,
    }


@router.post("/replays", status_code=202)
async def schedule_replay(
    payload: ReplayInput,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    context: AuthContext = JobsManager,
) -> dict[str, object]:
    _rate_limit(request, context.actor)
    async with request.app.state.session_factory() as session, session.begin():
        existing = await session.scalar(
            select(ReplayRequest).where(ReplayRequest.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return _replay_output(existing)
        connection = await session.get(SiteConnection, payload.connection_id)
        if connection is None or not connection.is_active:
            raise HTTPException(404, "active connection not found")
        if connection.delivery_mode != "push":
            raise HTTPException(409, "Pull sites can replay using their feed cursor")
        query = select(CanonicalNewsPackage).order_by(
            CanonicalNewsPackage.created_at, CanonicalNewsPackage.package_version
        )
        if payload.package_id:
            query = query.where(CanonicalNewsPackage.package_id == payload.package_id)
        if payload.from_time:
            query = query.where(CanonicalNewsPackage.created_at >= payload.from_time)
        if payload.to_time:
            query = query.where(CanonicalNewsPackage.created_at <= payload.to_time)
        if payload.min_version:
            query = query.where(CanonicalNewsPackage.package_version >= payload.min_version)
        if payload.max_version:
            query = query.where(CanonicalNewsPackage.package_version <= payload.max_version)
        packages = list((await session.execute(query)).scalars())
        replay = ReplayRequest(
            idempotency_key=idempotency_key,
            connection_id=payload.connection_id,
            requested_by=context.actor,
            from_time=payload.from_time,
            to_time=payload.to_time,
            package_id=payload.package_id,
            min_version=payload.min_version,
            max_version=payload.max_version,
            package_count=len(packages),
            status="scheduled" if packages else "completed",
        )
        session.add(replay)
        await session.flush()
        for package in packages:
            session.add(
                OutboxEvent(
                    event_type=CANONICAL_PACKAGE_CREATED,
                    payload={
                        "package_id": str(package.package_id),
                        "package_version": package.package_version,
                        "connection_ids": [str(payload.connection_id)],
                        "replay_request_id": str(replay.id),
                    },
                )
            )
        session.add(
            IntegrationAuditEvent(
                actor=context.actor,
                action="delivery.replay_scheduled",
                resource_type="replay_request",
                resource_id=str(replay.id),
                details={"connection_id": str(payload.connection_id), "packages": len(packages)},
            )
        )
    METRICS.increment("delivery_replay_total", action="scheduled")
    logger.info(
        "delivery_replay_scheduled",
        replay_request_id=str(replay.id),
        connection_id=str(payload.connection_id),
        package_count=len(packages),
        actor=context.actor,
    )
    return _replay_output(replay)


@router.get("/replays/{replay_request_id}")
async def get_replay(
    replay_request_id: UUID,
    request: Request,
    _: AuthContext = JobsManager,
) -> dict[str, object]:
    async with request.app.state.session_factory() as session:
        replay = await session.get(ReplayRequest, replay_request_id)
    if replay is None:
        raise HTTPException(404, "replay request not found")
    return _replay_output(replay)


@router.get("/deliveries/dead-letters")
async def list_dead_letters(
    request: Request, _: AuthContext = JobsManager
) -> list[dict[str, object]]:
    async with request.app.state.session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(Delivery)
                    .where(Delivery.status == "dead_lettered")
                    .order_by(Delivery.dead_lettered_at.desc())
                )
            ).scalars()
        )
    return [
        {
            "id": str(row.id),
            "connection_id": str(row.connection_id),
            "package_id": str(row.package_id),
            "package_version": row.package_version,
            "attempts": row.attempt_budget_used,
            "last_error": row.last_error,
            "dead_lettered_at": row.dead_lettered_at,
            "manual_retry_count": row.manual_retry_count,
        }
        for row in rows
    ]


@router.post("/deliveries/{delivery_id}/retry", status_code=202)
async def retry_dead_letter(
    delivery_id: UUID,
    request: Request,
    context: AuthContext = JobsManager,
) -> dict[str, object]:
    _rate_limit(request, context.actor)
    async with request.app.state.session_factory() as session, session.begin():
        delivery = await session.get(Delivery, delivery_id)
        if delivery is None or delivery.status != "dead_lettered":
            raise HTTPException(404, "dead-lettered delivery not found")
        delivery.status = "pending"
        delivery.attempt_budget_used = 0
        delivery.next_attempt_at = None
        delivery.dead_lettered_at = None
        delivery.last_error = None
        delivery.manual_retry_count += 1
        event = OutboxEvent(
            event_type=CANONICAL_PACKAGE_CREATED,
            payload={
                "package_id": str(delivery.package_id),
                "package_version": delivery.package_version,
                "connection_ids": [str(delivery.connection_id)],
            },
        )
        session.add(event)
        session.add(
            IntegrationAuditEvent(
                actor=context.actor,
                action="delivery.manual_retry",
                resource_type="delivery",
                resource_id=str(delivery.id),
                details={"manual_retry_count": delivery.manual_retry_count},
            )
        )
    METRICS.increment("delivery_manual_retry_total")
    return {"delivery_id": str(delivery.id), "status": "pending"}


@router.put("/connections/{connection_id}/signing-key")
async def rotate_signing_key(
    connection_id: UUID,
    payload: KeyRotationInput,
    request: Request,
    context: AuthContext = JobsManager,
) -> dict[str, object]:
    _rate_limit(request, context.actor)
    async with request.app.state.session_factory() as session, session.begin():
        connection = await session.get(SiteConnection, connection_id)
        if connection is None:
            raise HTTPException(404, "connection not found")
        if payload.key_id == connection.active_key_id:
            raise HTTPException(409, "key identifier is already active")
        connection.previous_key_id = connection.active_key_id
        connection.previous_hmac_secret = connection.hmac_secret
        connection.active_key_id = payload.key_id
        connection.hmac_secret = payload.secret
        session.add(
            IntegrationAuditEvent(
                actor=context.actor,
                action="connection.key_rotated",
                resource_type="site_connection",
                resource_id=str(connection.id),
                details={
                    "active_key_id": connection.active_key_id,
                    "previous_key_id": connection.previous_key_id,
                },
            )
        )
    METRICS.increment("hmac_key_rotation_total", action="rotated")
    return _key_output(connection)


@router.delete("/connections/{connection_id}/previous-signing-key", status_code=204)
async def retire_previous_signing_key(
    connection_id: UUID,
    request: Request,
    context: AuthContext = JobsManager,
) -> Response:
    _rate_limit(request, context.actor)
    async with request.app.state.session_factory() as session, session.begin():
        connection = await session.get(SiteConnection, connection_id)
        if connection is None:
            raise HTTPException(404, "connection not found")
        retired_key_id = connection.previous_key_id
        connection.previous_key_id = None
        connection.previous_hmac_secret = None
        session.add(
            IntegrationAuditEvent(
                actor=context.actor,
                action="connection.key_retired",
                resource_type="site_connection",
                resource_id=str(connection.id),
                details={"retired_key_id": retired_key_id},
            )
        )
    METRICS.increment("hmac_key_rotation_total", action="retired")
    return Response(status_code=204)


def _replay_output(row: ReplayRequest) -> dict[str, object]:
    return {
        "id": str(row.id),
        "status": row.status,
        "connection_id": str(row.connection_id),
        "package_count": row.package_count,
        "completed_count": row.completed_count,
        "failed_count": row.failed_count,
    }


def _key_output(connection: SiteConnection) -> dict[str, object]:
    return {
        "connection_id": str(connection.id),
        "active_key_id": connection.active_key_id,
        "previous_key_id": connection.previous_key_id,
    }
