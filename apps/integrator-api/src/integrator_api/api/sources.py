from __future__ import annotations

from typing import Any
from uuid import UUID

from common.auth import require_permission
from fastapi import APIRouter, Depends, HTTPException, Request
from integrator_domain.models import Source
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
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
    config: dict[str, Any] = Field(default_factory=dict)


class SourceOutput(SourceInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    is_active: bool
    status: str


@router.post("", response_model=SourceOutput, status_code=201)
async def create(payload: SourceInput, request: Request) -> SourceOutput:
    if payload.adapter_type not in {
        "rss",
        "html",
        "api",
        "browser",
        "youtube",
        "google_search",
        "gemini_search",
    }:
        raise HTTPException(422, "adapter type is not implemented")
    if payload.feed_url.username is not None or payload.feed_url.password is not None:
        raise HTTPException(422, "source URL credentials must use external secret storage")
    if payload.adapter_type == "html":
        try:
            validate_html_source_config(payload.config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if payload.adapter_type == "api":
        try:
            validate_api_source_config(payload.config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if payload.adapter_type == "browser":
        try:
            validate_html_source_config(payload.config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if payload.adapter_type == "youtube":
        try:
            validate_youtube_source_config(payload.config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if payload.adapter_type == "google_search":
        try:
            validate_google_search_source_config(payload.config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if payload.adapter_type == "gemini_search":
        try:
            validate_gemini_search_source_config(payload.config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    async with request.app.state.session_factory() as session:
        source = Source(
            name=payload.name,
            feed_url=str(payload.feed_url),
            adapter_type=payload.adapter_type,
            config=payload.config,
            poll_interval_seconds=payload.poll_interval_seconds,
        )
        session.add(source)
        await session.commit()
        return SourceOutput.model_validate(source)


def validate_html_source_config(config: dict[str, Any]) -> None:
    required = {"item_selector", "url_selector", "title_selector", "content_selector"}
    missing = sorted(
        key for key in required if not isinstance(config.get(key), str) or not config[key]
    )
    if missing:
        raise ValueError(f"HTML source config requires: {', '.join(missing)}")
    for key, value in config.items():
        if key.endswith("_selector") and not isinstance(value, str):
            raise ValueError(f"HTML source config {key} must be a selector string")


def validate_api_source_config(config: dict[str, Any]) -> None:
    mapping = config.get("mapping")
    if not isinstance(config.get("items_path"), str) or not isinstance(mapping, dict):
        raise ValueError("API source config requires items_path and mapping")
    missing = sorted(key for key in {"id", "title", "url"} if not isinstance(mapping.get(key), str))
    if missing:
        raise ValueError(f"API source mapping requires: {', '.join(missing)}")
    if str(config.get("method", "GET")).upper() not in {"GET", "POST"}:
        raise ValueError("API source method must be GET or POST")
    headers = config.get("headers", {})
    if not isinstance(headers, dict):
        raise ValueError("API source headers must be an object")
    if any("authorization" in key.lower() or "api-key" in key.lower() for key in headers):
        raise ValueError("API secrets must use auth_env, not stored headers")


def validate_youtube_source_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("api_key_env"), str) or not config["api_key_env"]:
        raise ValueError("YouTube source config requires api_key_env")
    if not any(
        isinstance(config.get(key), str) and config[key]
        for key in ("channel_id", "channel_url", "playlist_id")
    ):
        raise ValueError("YouTube source config requires channel_id, channel_url, or playlist_id")
    if any(key.lower() in {"api_key", "key", "authorization"} for key in config):
        raise ValueError("YouTube API key must use api_key_env, not source config")


def _validate_search_common(config: dict[str, Any], name: str) -> None:
    if not isinstance(config.get("api_key_env"), str) or not config["api_key_env"]:
        raise ValueError(f"{name} source config requires api_key_env")
    if not isinstance(config.get("query"), str) or not config["query"]:
        raise ValueError(f"{name} source config requires query")
    if any(key.lower() in {"api_key", "key", "authorization"} for key in config):
        raise ValueError(f"{name} API key must use api_key_env, not source config")


def validate_google_search_source_config(config: dict[str, Any]) -> None:
    _validate_search_common(config, "Google Search")
    if not isinstance(config.get("search_engine_id"), str) or not config["search_engine_id"]:
        raise ValueError("Google Search source config requires search_engine_id")


def validate_gemini_search_source_config(config: dict[str, Any]) -> None:
    _validate_search_common(config, "Gemini Search")


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
