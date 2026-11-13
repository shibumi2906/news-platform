from __future__ import annotations
# ruff: noqa: E501,I001

from typing import Any
from datetime import datetime
import asyncio
import ipaddress
import socket
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from common.auth import require_permission
from common.time import utc_now
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from integrator_domain.models import Source
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select
from source_worker.rss import parse_rss_feed
from source_worker.youtube import collect_youtube_source

router = APIRouter(
    prefix="/api/v1/sources",
    tags=["sources"],
    dependencies=[Depends(require_permission("sources:manage"))],
)


class SourceInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    feed_url: HttpUrl
    adapter_type: str = "rss"
    poll_interval_seconds: int = Field(default=300, ge=30)
    config: dict[str, Any] = Field(default_factory=dict)


class SourceOutput(SourceInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    is_active: bool
    status: str
    health_status: str
    health_reason: str | None
    last_success_at: datetime | None


@router.post("/preview")
async def activation_preview(payload: SourceInput) -> dict[str, object]:
    """Fail closed before a source can be activated; network fetch happens in worker."""
    if payload.feed_url.username is not None or payload.feed_url.password is not None:
        raise HTTPException(422, "source URL credentials must use external secret storage")
    governance = payload.config.get("governance", {})
    if not isinstance(governance, dict):
        raise HTTPException(422, "governance must be an object")
    rate = governance.get("requests_per_minute", 60)
    if not isinstance(rate, int) or not 1 <= rate <= 600:
        raise HTTPException(422, "requests_per_minute must be between 1 and 600")
    return {"allowed": True, "adapter_type": payload.adapter_type, "requests_per_minute": rate, "requires_robots_review": bool(governance.get("respect_robots", True)), "requires_tos_review": bool(governance.get("tos_accepted", False))}


@router.post("", response_model=SourceOutput, status_code=201)
async def create(payload: SourceInput, request: Request) -> SourceOutput:
    validate_source(payload)
    async with request.app.state.session_factory() as session:
        source = Source(**source_values(payload))
        session.add(source)
        await session.commit()
        return SourceOutput.model_validate(source)


def source_values(payload: SourceInput) -> dict[str, Any]:
    return {**payload.model_dump(), "feed_url": str(payload.feed_url)}


def configure_youtube(payload: SourceInput) -> None:
    url = urlsplit(str(payload.feed_url))
    if url.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        raise HTTPException(422, "Enter a YouTube channel or playlist URL")
    segments = url.path.strip("/").split("/")
    playlist = parse_qs(url.query).get("list", [""])[0]
    target: dict[str, str]
    if playlist and url.path in {"/playlist", "/watch"}:
        target = {"playlist_id": playlist}
    elif segments[0].startswith("@") and len(segments[0]) > 1:
        target = {"channel_url": f"https://www.youtube.com/{segments[0]}"}
    elif len(segments) >= 2 and segments[0] in {"channel", "user"} and segments[1]:
        target = {"channel_url": f"https://www.youtube.com/{segments[0]}/{segments[1]}"}
    else:
        raise HTTPException(422, "Enter a YouTube channel or playlist URL")
    payload.config = {
        **{key: value for key, value in payload.config.items()
           if key not in {"playlist_id", "channel_id", "channel_url"}},
        **target,
        "api_key_env": "YOUTUBE_API_KEY",
    }


@router.post("/sample")
async def sample_source(payload: SourceInput, request: Request) -> dict[str, Any]:
    if not request.app.state.integration_limiter.allow("source-sample"):
        raise HTTPException(429, "Too many source checks")
    if payload.adapter_type not in {"rss", "youtube"}:
        raise HTTPException(422, "Preview supports RSS, Atom and YouTube")
    if payload.feed_url.username is not None or payload.feed_url.password is not None:
        raise HTTPException(422, "Source URLs cannot contain credentials")
    source_id, now = uuid4(), utc_now()
    try:
        async with asyncio.timeout(15), httpx.AsyncClient(trust_env=False, timeout=8) as client:
            if payload.adapter_type == "youtube":
                payload.config = {}
                configure_youtube(payload)
                items, error = await collect_youtube_source(
                    client, source_id=source_id, config={**payload.config, "page_size": 5},
                    fetched_at=now, user_agent="Path News", timeout_seconds=5,
                )
                if error:
                    raise HTTPException(502, error)
            else:
                body = await _sample_feed(client, str(payload.feed_url))
                items = parse_rss_feed(body, source_id=source_id, fetched_at=now)
    except (TimeoutError, httpx.HTTPError, OSError) as exc:
        raise HTTPException(502, "Could not read source") from exc
    return {"items": [
        {"title": item.title, "url": str(item.url), "text": (item.body or item.excerpt or "")[:12000]}
        for item in items[:5]
    ]}


async def _sample_feed(client: httpx.AsyncClient, value: str) -> bytes:
    url = httpx.URL(value)
    if url.port not in {None, 80, 443}:
        raise HTTPException(422, "Use a public RSS or Atom URL on a standard HTTP port")
    addresses = await asyncio.get_running_loop().getaddrinfo(
        url.raw_host.decode(), url.port or (443 if url.scheme == "https" else 80),
        type=socket.SOCK_STREAM,
    )
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise HTTPException(422, "Feed must be hosted on a public address")
    # Connect to the validated address while retaining hostname verification for TLS.
    target = url.copy_with(host=addresses[0][4][0])
    async with client.stream(
        "GET", target, headers={"Host": url.netloc.decode()},
        extensions={"sni_hostname": url.raw_host.decode()},
    ) as response:
        if response.is_redirect:
            raise HTTPException(422, "Use the final feed URL after redirects")
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=16384):
            body.extend(chunk)
            if len(body) > 2 * 1024 * 1024:
                raise HTTPException(422, "Feed is larger than the preview limit")
    return bytes(body)


def validate_source(payload: SourceInput) -> None:
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
        if not any(key in payload.config for key in ("playlist_id", "channel_id", "channel_url")):
            configure_youtube(payload)
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


@router.put("/{source_id}", response_model=SourceOutput)
async def update_source(source_id: UUID, payload: SourceInput, request: Request) -> SourceOutput:
    async with request.app.state.session_factory() as session:
        source = await session.get(Source, source_id)
        if source is None:
            raise HTTPException(404, "source not found")
        if not payload.config and source.adapter_type == payload.adapter_type:
            payload.config = dict(source.config)
            if payload.adapter_type == "youtube" and str(payload.feed_url) != source.feed_url:
                configure_youtube(payload)
        validate_source(payload)
        if (source.feed_url, source.adapter_type, source.config) != (
            str(payload.feed_url), payload.adapter_type, payload.config
        ):
            source.etag = source.last_modified = source.last_error = source.health_reason = None
            source.next_retry_at = source.last_success_at = None
            source.consecutive_failures = 0
            source.health_status = "healthy"
        for key, value in source_values(payload).items():
            setattr(source, key, value)
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
