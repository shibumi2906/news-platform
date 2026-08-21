"""Distribution Admin API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.auth import require_permission
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from site_domain.models import DistributionAttempt, DistributionChannel, DistributionJob
from sqlalchemy import select

from site_api.distribution import (
    SUPPORTED_CHANNELS,
    create_channel,
    schedule_distribution,
    validate_provider_config,
)

router = APIRouter(
    prefix="/api/v1/admin/distribution",
    tags=["distribution"],
    dependencies=[Depends(require_permission("distribution:manage"))],
)


class ChannelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str
    account_key: str = Field(min_length=1, max_length=255)
    credential_ref: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{1,80}$")
    config: dict[str, Any] = Field(default_factory=dict)


class ChannelResponse(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    account_key: str
    credential_ref: str | None
    config: dict[str, Any]
    is_active: bool


class ScheduleRequest(BaseModel):
    channel_id: uuid.UUID
    article_version_id: uuid.UUID
    translation_version_id: uuid.UUID | None = None
    media_asset_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=255)
    max_attempts: int = Field(default=5, ge=1, le=10)


def _channel(item: DistributionChannel) -> ChannelResponse:
    return ChannelResponse(
        id=item.id,
        name=item.name,
        kind=item.kind,
        account_key=item.account_key,
        credential_ref=item.credential_ref,
        config=item.config,
        is_active=item.is_active,
    )


@router.get("/channels", response_model=list[ChannelResponse])
async def list_channels(request: Request) -> list[ChannelResponse]:
    async with request.app.state.session_factory() as session:
        items = (
            await session.execute(select(DistributionChannel).order_by(DistributionChannel.name))
        ).scalars()
        return [_channel(item) for item in items]


@router.post("/channels", response_model=ChannelResponse, status_code=201)
async def add_channel(payload: ChannelRequest, request: Request) -> ChannelResponse:
    async with request.app.state.session_factory() as session:
        try:
            item = await create_channel(session, **payload.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return _channel(item)


@router.put("/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: uuid.UUID, payload: ChannelRequest, request: Request
) -> ChannelResponse:
    async with request.app.state.session_factory() as session:
        item = await session.get(DistributionChannel, channel_id)
        if item is None:
            raise HTTPException(404, "distribution channel not found")
        if payload.kind not in SUPPORTED_CHANNELS:
            raise HTTPException(422, "unsupported distribution channel kind")
        try:
            validate_provider_config(payload.kind, payload.config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        item.name = payload.name
        item.kind = payload.kind
        item.account_key = payload.account_key
        item.credential_ref = payload.credential_ref
        item.config = payload.config
        await session.commit()
        return _channel(item)


@router.post("/channels/{channel_id}/{action}", response_model=ChannelResponse)
async def channel_state(channel_id: uuid.UUID, action: str, request: Request) -> ChannelResponse:
    if action not in {"activate", "deactivate"}:
        raise HTTPException(404, "unknown channel action")
    async with request.app.state.session_factory() as session:
        item = await session.get(DistributionChannel, channel_id)
        if item is None:
            raise HTTPException(404, "distribution channel not found")
        item.is_active = action == "activate"
        await session.commit()
        return _channel(item)


@router.post("/jobs", response_model=dict[str, Any], status_code=201)
async def schedule_job(payload: ScheduleRequest, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        try:
            job, created = await schedule_distribution(session, **payload.model_dump())
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {
            "id": str(job.id),
            "status": job.status,
            "created": created,
            "scheduled_at": job.scheduled_at,
            "attempt_count": job.attempt_count,
            "error_code": job.error_code,
        }


@router.get("/jobs", response_model=list[dict[str, Any]])
async def list_jobs(
    request: Request, limit: int = Query(default=100, ge=1, le=200)
) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        jobs = (
            await session.execute(
                select(DistributionJob).order_by(DistributionJob.created_at.desc()).limit(limit)
            )
        ).scalars()
        return [
            {
                "id": str(job.id),
                "channel_id": str(job.channel_id),
                "article_version_id": str(job.article_version_id),
                "status": job.status,
                "scheduled_at": job.scheduled_at,
                "next_attempt_at": job.next_attempt_at,
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
                "external_publication_id": job.external_publication_id,
                "external_url": job.external_url,
                "error_code": job.error_code,
                "error_message": job.error_message,
            }
            for job in jobs
        ]


@router.get("/jobs/{job_id}/attempts", response_model=list[dict[str, Any]])
async def list_attempts(job_id: uuid.UUID, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        attempts = (
            await session.execute(
                select(DistributionAttempt)
                .where(DistributionAttempt.job_id == job_id)
                .order_by(DistributionAttempt.attempt_number)
            )
        ).scalars()
        return [
            {
                "id": str(item.id),
                "attempt_number": item.attempt_number,
                "status": item.status,
                "latency_ms": item.latency_ms,
                "error_code": item.error_code,
                "diagnostics": item.diagnostics,
            }
            for item in attempts
        ]
