from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from site_api.editorial import (
    create_article_from_package,
    create_version,
    publish,
    review,
    submit_for_review,
    unpublish,
)

router = APIRouter(prefix="/api/v1", tags=["editorial"])


class ArticleResponse(BaseModel):
    id: UUID
    status: str
    lock_version: int
    latest_version_number: int


class CreateArticleRequest(BaseModel):
    incoming_package_version_id: UUID


class VersionRequest(BaseModel):
    content: dict[str, Any]
    expected_lock_version: int
    correction_explanation: str | None = None


class ActionRequest(BaseModel):
    expected_lock_version: int
    reason: str | None = None


class PublishRequest(BaseModel):
    expected_lock_version: int
    scheduled_at: datetime | None = None


def _response(article: Any) -> ArticleResponse:
    return ArticleResponse(
        id=article.id,
        status=article.status,
        lock_version=article.lock_version,
        latest_version_number=article.latest_version_number,
    )


@router.post("/articles", response_model=ArticleResponse, status_code=201)
async def create_article(
    request: Request, payload: CreateArticleRequest, x_actor_id: str = Header(alias="X-Actor-Id")
) -> ArticleResponse:
    async with request.app.state.session_factory() as session:
        return _response(
            await create_article_from_package(
                session,
                incoming_package_version_id=payload.incoming_package_version_id,
                actor_id=x_actor_id,
            )
        )


@router.post("/articles/{article_id}/versions", response_model=ArticleResponse)
async def add_version(
    article_id: UUID,
    request: Request,
    payload: VersionRequest,
    x_actor_id: str = Header(alias="X-Actor-Id"),
) -> ArticleResponse:
    async with request.app.state.session_factory() as session:
        return _response(
            await create_version(
                session,
                article_id=article_id,
                content=payload.content,
                actor_id=x_actor_id,
                expected_lock_version=payload.expected_lock_version,
                correction_explanation=payload.correction_explanation,
            )
        )


@router.post("/articles/{article_id}/submit-review", response_model=ArticleResponse)
async def submit(
    article_id: UUID,
    request: Request,
    payload: ActionRequest,
    x_actor_id: str = Header(alias="X-Actor-Id"),
) -> ArticleResponse:
    async with request.app.state.session_factory() as session:
        return _response(
            await submit_for_review(
                session,
                article_id=article_id,
                actor_id=x_actor_id,
                expected_lock_version=payload.expected_lock_version,
            )
        )


@router.post("/articles/{article_id}/reviews/approve", response_model=ArticleResponse)
async def approve(
    article_id: UUID,
    request: Request,
    payload: ActionRequest,
    x_actor_id: str = Header(alias="X-Actor-Id"),
) -> ArticleResponse:
    async with request.app.state.session_factory() as session:
        return _response(
            await review(
                session,
                article_id=article_id,
                actor_id=x_actor_id,
                expected_lock_version=payload.expected_lock_version,
                approve=True,
                reason=payload.reason,
            )
        )


@router.post("/articles/{article_id}/reviews/reject", response_model=ArticleResponse)
async def reject(
    article_id: UUID,
    request: Request,
    payload: ActionRequest,
    x_actor_id: str = Header(alias="X-Actor-Id"),
) -> ArticleResponse:
    async with request.app.state.session_factory() as session:
        return _response(
            await review(
                session,
                article_id=article_id,
                actor_id=x_actor_id,
                expected_lock_version=payload.expected_lock_version,
                approve=False,
                reason=payload.reason,
            )
        )


@router.post("/articles/{article_id}/publication", response_model=ArticleResponse)
async def create_publication(
    article_id: UUID,
    request: Request,
    payload: PublishRequest,
    x_actor_id: str = Header(alias="X-Actor-Id"),
) -> ArticleResponse:
    async with request.app.state.session_factory() as session:
        return _response(
            await publish(
                session,
                article_id=article_id,
                actor_id=x_actor_id,
                expected_lock_version=payload.expected_lock_version,
                scheduled_at=payload.scheduled_at,
            )
        )


@router.post("/articles/{article_id}/unpublish", response_model=ArticleResponse)
async def remove_publication(
    article_id: UUID, request: Request, payload: ActionRequest
) -> ArticleResponse:
    async with request.app.state.session_factory() as session:
        return _response(
            await unpublish(
                session, article_id=article_id, expected_lock_version=payload.expected_lock_version
            )
        )
