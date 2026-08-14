"""YouTube Data API v3 source connector."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

import httpx
from contracts.source import SourceCandidate

from source_worker.api import _request_json
from source_worker.rss import canonicalize_url

_API_ROOT = "https://www.googleapis.com/youtube/v3"


def _date(value: object, fallback: datetime) -> datetime:
    if not isinstance(value, str):
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return fallback


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _number(config: Mapping[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


async def _channel_id(
    client: httpx.AsyncClient,
    *,
    api_root: str,
    channel_url: str,
    api_key: str,
    user_agent: str,
    timeout_seconds: float,
) -> tuple[str | None, str | None]:
    path = urlparse(channel_url).path.strip("/")
    if path.startswith("channel/"):
        return path.removeprefix("channel/") or None, None
    parameter, value = (
        ("forHandle", path.removeprefix("@"))
        if path.startswith("@")
        else (
            "forUsername",
            path.removeprefix("user/"),
        )
    )
    if not value:
        return None, "invalid_youtube_channel_url"
    response, error = await _request_json(
        client,
        url=f"{api_root}/channels",
        method="GET",
        headers={"User-Agent": user_agent},
        params={"part": "id", parameter: value, "key": api_key},
        body=None,
        timeout_seconds=timeout_seconds,
    )
    if error:
        return None, error
    items = _mapping(response).get("items")
    if not isinstance(items, list) or not items or not isinstance(items[0], Mapping):
        return None, "youtube_channel_not_found"
    return _text(items[0].get("id")), None


async def collect_youtube_source(
    client: httpx.AsyncClient,
    *,
    source_id: UUID,
    config: Mapping[str, object],
    fetched_at: datetime,
    user_agent: str,
    timeout_seconds: float,
) -> tuple[list[SourceCandidate], str | None]:
    """Collect channel or playlist videos; a malformed video never aborts a page."""
    env_name = config.get("api_key_env")
    api_key = os.getenv(str(env_name)) if isinstance(env_name, str) else None
    if not api_key:
        return [], "missing_youtube_api_key"
    api_root = str(config.get("api_root", _API_ROOT)).rstrip("/")
    playlist_id = _text(config.get("playlist_id"))
    channel_id = _text(config.get("channel_id"))
    headers = {"User-Agent": user_agent}
    if not playlist_id and not channel_id:
        channel_url = _text(config.get("channel_url"))
        if not channel_url:
            return [], "missing_youtube_target"
        channel_id, error = await _channel_id(
            client,
            api_root=api_root,
            channel_url=channel_url,
            api_key=api_key,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
        )
        if error or not channel_id:
            return [], error or "youtube_channel_not_found"

    endpoint = "playlistItems" if playlist_id else "search"
    params = {
        "part": "snippet",
        "maxResults": str(min(50, max(1, _number(config, "page_size", 50)))),
        "key": api_key,
    }
    if playlist_id:
        params["playlistId"] = playlist_id
    else:
        params.update({"channelId": channel_id or "", "type": "video", "order": "date"})
    candidates: list[SourceCandidate] = []
    seen: set[str] = set()
    page_token: str | None = None
    max_pages = max(1, _number(config, "max_pages", 1))
    for _ in range(max_pages):
        request_params = {**params, **({"pageToken": page_token} if page_token else {})}
        response, error = await _request_json(
            client,
            url=f"{api_root}/{endpoint}",
            method="GET",
            headers=headers,
            params=request_params,
            body=None,
            timeout_seconds=timeout_seconds,
        )
        if error:
            return candidates, error
        payload = _mapping(response)
        items = payload.get("items")
        if not isinstance(items, list):
            return candidates, "invalid_youtube_response"
        for item in items:
            if not isinstance(item, Mapping):
                continue
            snippet = _mapping(item.get("snippet"))
            item_id = _mapping(item.get("id"))
            content_details = _mapping(item.get("contentDetails"))
            video_id = _text(item_id.get("videoId")) or _text(content_details.get("videoId"))
            title = _text(snippet.get("title"))
            if not video_id or not title or video_id in seen:
                continue
            seen.add(video_id)
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            thumbnails = _mapping(snippet.get("thumbnails"))
            candidates.append(
                SourceCandidate(
                    source_id=source_id,
                    external_id=video_id,
                    url=video_url,
                    canonical_url=canonicalize_url(video_url),
                    title=title,
                    excerpt=_text(snippet.get("description")),
                    body=_text(snippet.get("description")),
                    author=_text(snippet.get("channelTitle")),
                    language=_text(snippet.get("defaultLanguage"))
                    or _text(config.get("language"))
                    or "en",
                    published_at=_date(snippet.get("publishedAt"), fetched_at),
                    fetched_at=fetched_at,
                    raw={
                        "adapter": "youtube",
                        "video_id": video_id,
                        "channel_id": _text(snippet.get("channelId")) or channel_id,
                        "thumbnails": dict(thumbnails),
                    },
                )
            )
        page_token = _text(payload.get("nextPageToken"))
        if not page_token:
            break
    return candidates, None
