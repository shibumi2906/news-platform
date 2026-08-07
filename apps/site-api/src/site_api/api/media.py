"""Media library, generation, meme, and video foundation endpoints."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime
from typing import Any

from common.auth import require_admin_api_token
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from site_domain.models import (
    ArticleMediaLink,
    MediaAsset,
    MediaGenerationRun,
    MemeTemplate,
)
from sqlalchemy import select

from site_api.media_generation import MediaProviderError
from site_api.media_service import (
    AssetInput,
    create_meme,
    create_video_project,
    generate_article_images,
    select_media,
    store_asset,
)

router = APIRouter(
    prefix="/api/v1/admin/media",
    tags=["media"],
    dependencies=[Depends(require_admin_api_token)],
)


class MediaAssetResponse(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    duration_ms: int | None
    source_event_id: uuid.UUID | None
    source_url: str | None
    rights: dict[str, Any]
    provenance: dict[str, Any]
    ai_generated: bool
    created_at: datetime


class UploadRequest(BaseModel):
    content_base64: str
    mime_type: str = Field(pattern=r"^(image|video|audio)/[-+.a-zA-Z0-9]+$")
    kind: str = "original"
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)
    source_event_id: uuid.UUID | None = None
    source_url: str | None = None
    rights: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    article_version_id: uuid.UUID
    variants: int = Field(default=3, ge=1, le=4)


class SelectRequest(BaseModel):
    article_version_id: uuid.UUID
    translation_version_id: uuid.UUID | None = None
    role: str = Field(default="hero", pattern=r"^[a-z_]{2,32}$")


class MemeTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_asset_id: uuid.UUID
    layout: dict[str, Any] = Field(default_factory=dict)


class MemeRequest(BaseModel):
    template_id: uuid.UUID
    article_version_id: uuid.UUID
    mode: str = Field(pattern="^(manual|ai)$")
    caption: str | None = Field(default=None, max_length=280)


class VideoRequest(BaseModel):
    article_version_id: uuid.UUID


def _asset(item: MediaAsset) -> MediaAssetResponse:
    return MediaAssetResponse(
        id=item.id,
        kind=item.kind,
        status=item.status,
        mime_type=item.mime_type,
        size_bytes=item.size_bytes,
        width=item.width,
        height=item.height,
        duration_ms=item.duration_ms,
        source_event_id=item.source_event_id,
        source_url=item.source_url,
        rights=item.rights,
        provenance=item.provenance,
        ai_generated=item.ai_generated,
        created_at=item.created_at,
    )


@router.get("", response_model=list[MediaAssetResponse])
async def list_media(
    request: Request, limit: int = Query(default=100, ge=1, le=200)
) -> list[MediaAssetResponse]:
    async with request.app.state.session_factory() as session:
        items = (
            await session.execute(
                select(MediaAsset).order_by(MediaAsset.created_at.desc()).limit(limit)
            )
        ).scalars()
        return [_asset(item) for item in items]


@router.post("", response_model=MediaAssetResponse, status_code=201)
async def upload_media(payload: UploadRequest, request: Request) -> MediaAssetResponse:
    try:
        data = base64.b64decode(payload.content_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(422, "invalid base64 media content") from exc
    if not data or len(data) > request.app.state.settings.media_upload_max_bytes:
        raise HTTPException(413, "media content is empty or exceeds configured limit")
    async with request.app.state.session_factory() as session:
        item = await store_asset(
            session,
            request.app.state.object_storage,
            AssetInput(
                data=data,
                mime_type=payload.mime_type,
                kind=payload.kind,
                width=payload.width,
                height=payload.height,
                duration_ms=payload.duration_ms,
                source_event_id=payload.source_event_id,
                source_url=payload.source_url,
                rights=payload.rights,
                provenance=payload.provenance,
            ),
        )
        return _asset(item)


@router.get("/{asset_id}/content")
async def media_content(asset_id: uuid.UUID, request: Request) -> Response:
    async with request.app.state.session_factory() as session:
        asset = await session.get(MediaAsset, asset_id)
        if asset is None or asset.status != "ready":
            raise HTTPException(404, "media asset not found")
        data, mime_type = await request.app.state.object_storage.get(asset.object_key)
        return Response(
            data, media_type=mime_type, headers={"Cache-Control": "private, max-age=60"}
        )


@router.post("/generate", response_model=dict[str, Any], status_code=201)
async def generate_media(payload: GenerateRequest, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        try:
            run, assets = await generate_article_images(
                session,
                request.app.state.object_storage,
                request.app.state.media_gateway,
                article_version_id=payload.article_version_id,
                variants=payload.variants,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except MediaProviderError as exc:
            raise HTTPException(422 if not exc.retryable else 503, exc.code) from exc
        return {
            "run_id": str(run.id),
            "status": run.status,
            "assets": [_asset(item).model_dump(mode="json") for item in assets],
        }


@router.post("/{asset_id}/select", response_model=dict[str, Any])
async def choose_media(
    asset_id: uuid.UUID, payload: SelectRequest, request: Request
) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        try:
            link = await select_media(
                session,
                asset_id=asset_id,
                article_version_id=payload.article_version_id,
                translation_version_id=payload.translation_version_id,
                role=payload.role,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"link_id": str(link.id), "selected": link.selected}


@router.get("/links", response_model=list[dict[str, Any]])
async def list_links(request: Request, article_version_id: uuid.UUID) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        links = (
            await session.execute(
                select(ArticleMediaLink).where(
                    ArticleMediaLink.article_version_id == article_version_id
                )
            )
        ).scalars()
        return [
            {
                "id": str(link.id),
                "media_asset_id": str(link.media_asset_id),
                "translation_version_id": str(link.translation_version_id)
                if link.translation_version_id
                else None,
                "role": link.role,
                "selected": link.selected,
                "sort_order": link.sort_order,
            }
            for link in links
        ]


@router.post("/meme-templates", response_model=dict[str, Any], status_code=201)
async def create_meme_template(payload: MemeTemplateRequest, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        if await session.get(MediaAsset, payload.base_asset_id) is None:
            raise HTTPException(404, "base media asset not found")
        item = MemeTemplate(
            name=payload.name, base_asset_id=payload.base_asset_id, layout=payload.layout
        )
        session.add(item)
        await session.commit()
        return {"id": str(item.id), "name": item.name, "layout": item.layout}


@router.get("/meme-templates", response_model=list[dict[str, Any]])
async def list_meme_templates(request: Request) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        items = (await session.execute(select(MemeTemplate).order_by(MemeTemplate.name))).scalars()
        return [
            {
                "id": str(item.id),
                "name": item.name,
                "base_asset_id": str(item.base_asset_id),
                "layout": item.layout,
                "is_active": item.is_active,
            }
            for item in items
        ]


@router.post("/memes", response_model=dict[str, Any], status_code=201)
async def generate_meme(payload: MemeRequest, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        try:
            item = await create_meme(
                session,
                request.app.state.object_storage,
                template_id=payload.template_id,
                article_version_id=payload.article_version_id,
                mode=payload.mode,
                caption=payload.caption,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {
            "id": str(item.id),
            "asset_id": str(item.output_asset_id),
            "version_number": item.version_number,
            "mode": item.mode,
        }


@router.post("/video-projects", response_model=dict[str, Any], status_code=201)
async def video_project(payload: VideoRequest, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        try:
            project = await create_video_project(
                session, article_version_id=payload.article_version_id
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {
            "id": str(project.id),
            "status": project.status,
            "script": project.script,
            "storyboard": project.storyboard,
            "provider": project.provider,
            "model": project.model,
            "telemetry": project.telemetry,
        }


@router.get("/telemetry", response_model=list[dict[str, Any]])
async def media_telemetry(request: Request) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        runs = (
            await session.execute(
                select(MediaGenerationRun).order_by(MediaGenerationRun.created_at.desc()).limit(100)
            )
        ).scalars()
        return [
            {
                "id": str(run.id),
                "operation": run.operation,
                "provider": run.provider,
                "model": run.model,
                "status": run.status,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "estimated_cost_usd": str(run.estimated_cost_usd),
                "latency_ms": run.latency_ms,
                "error_code": run.error_code,
            }
            for run in runs
        ]
