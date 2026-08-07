from __future__ import annotations

from uuid import UUID

from common.auth import require_permission
from fastapi import APIRouter, Depends, HTTPException, Request
from integrator_domain.models import Source
from pydantic import BaseModel, ConfigDict, HttpUrl
from sqlalchemy import select

router = APIRouter(
    prefix="/api/v1/sources",
    tags=["sources"],
    dependencies=[Depends(require_permission("sources:manage"))],
)


class SourceInput(BaseModel):
    name: str
    feed_url: HttpUrl
    adapter_type: str = "rss"
    poll_interval_seconds: int = 300


class SourceOutput(SourceInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    is_active: bool
    status: str


@router.post("", response_model=SourceOutput, status_code=201)
async def create(payload: SourceInput, request: Request) -> SourceOutput:
    if payload.adapter_type not in {"rss", "html"}:
        raise HTTPException(422, "adapter type is not implemented")
    async with request.app.state.session_factory() as session:
        source = Source(
            name=payload.name,
            feed_url=str(payload.feed_url),
            adapter_type=payload.adapter_type,
            poll_interval_seconds=payload.poll_interval_seconds,
        )
        session.add(source)
        await session.commit()
        return SourceOutput.model_validate(source)


@router.get("", response_model=list[SourceOutput])
async def list_sources(request: Request) -> list[Source]:
    async with request.app.state.session_factory() as session:
        return list((await session.execute(select(Source))).scalars())


@router.post("/{source_id}/activate", response_model=SourceOutput)
async def activate(source_id: UUID, request: Request) -> SourceOutput:
    async with request.app.state.session_factory() as session:
        source = await session.get(Source, source_id)
        if source is None:
            raise HTTPException(404, "source not found")
        source.is_active, source.status = True, "active"
        await session.commit()
        return SourceOutput.model_validate(source)


@router.post("/{source_id}/deactivate", response_model=SourceOutput)
async def deactivate(source_id: UUID, request: Request) -> SourceOutput:
    async with request.app.state.session_factory() as session:
        source = await session.get(Source, source_id)
        if source is None:
            raise HTTPException(404, "source not found")
        source.is_active, source.status = False, "disabled"
        await session.commit()
        return SourceOutput.model_validate(source)
