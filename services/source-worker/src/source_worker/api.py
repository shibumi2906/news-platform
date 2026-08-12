"""Configuration-driven JSON HTTP API source connector."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urljoin
from uuid import UUID

import httpx
from contracts.source import SourceCandidate

from source_worker.rss import canonicalize_url

_RETRYABLE = {408, 429, 500, 502, 503, 504}


def _path(value: object, expression: str) -> object | None:
    current = value
    for part in expression.split("."):
        if isinstance(current, Mapping):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _text(item: Mapping[str, object], path: str | None) -> str | None:
    value = _path(item, path) if path else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _date(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return fallback


def _headers(config: Mapping[str, object], user_agent: str) -> tuple[dict[str, str], str | None]:
    headers = {"User-Agent": user_agent}
    configured = config.get("headers", {})
    if isinstance(configured, Mapping):
        headers.update({str(key): str(value) for key, value in configured.items()})
    env_name = config.get("auth_env")
    if not env_name:
        return headers, None
    secret = os.environ.get(str(env_name))
    if not secret:
        return headers, "missing_api_secret"
    header = str(config.get("auth_header", "Authorization"))
    prefix = str(config.get("auth_prefix", "Bearer "))
    headers[header] = f"{prefix}{secret}"
    return headers, None


async def _request_json(
    client: httpx.AsyncClient,
    *,
    url: str,
    method: str,
    headers: dict[str, str],
    params: dict[str, str],
    body: object,
    timeout_seconds: float,
    max_attempts: int = 3,
) -> tuple[object | None, str | None]:
    for attempt in range(max_attempts):
        response: httpx.Response | None = None
        try:
            response = await client.request(
                method, url, headers=headers, params=params, json=body, timeout=timeout_seconds
            )
        except httpx.HTTPError as exc:
            error = f"transport_{type(exc).__name__.lower()}"
        else:
            if response.status_code not in _RETRYABLE:
                if response.status_code >= 400:
                    return None, f"http_{response.status_code}"
                try:
                    return response.json(), None
                except ValueError:
                    return None, "invalid_json"
            error = f"http_{response.status_code}"
        if attempt + 1 < max_attempts:
            retry_after = response.headers.get("Retry-After") if response is not None else None
            await asyncio.sleep(0 if retry_after == "0" else 1)
    return None, error


async def collect_api_source(
    client: httpx.AsyncClient,
    *,
    source_id: UUID,
    base_url: str,
    config: Mapping[str, object],
    fetched_at: datetime,
    user_agent: str,
    timeout_seconds: float,
) -> tuple[list[SourceCandidate], str | None]:
    """Collect paginated JSON records into candidates; malformed records are skipped."""
    headers, error = _headers(config, user_agent)
    if error:
        return [], error
    mapping = config.get("mapping")
    if not isinstance(mapping, Mapping):
        return [], "invalid_api_mapping"
    raw_params = config.get("query_params", {})
    params = (
        {str(key): str(value) for key, value in raw_params.items()}
        if isinstance(raw_params, Mapping)
        else {}
    )
    pagination = config.get("pagination", {})
    pagination = pagination if isinstance(pagination, Mapping) else {}
    max_pages = int(pagination.get("max_pages", 1))
    page_param = str(pagination.get("page_param", "page"))
    page = int(pagination.get("start", 1))
    next_path = pagination.get("next_path")
    url = str(config.get("endpoint_url", base_url))
    method = str(config.get("method", "GET")).upper()
    body = config.get("json_body")
    items_path = config.get("items_path")
    if not isinstance(items_path, str):
        return [], "invalid_api_items_path"
    candidates: list[SourceCandidate] = []
    for _ in range(max(1, max_pages)):
        if pagination:
            params[page_param] = str(page)
        response, error = await _request_json(
            client,
            url=url,
            method=method,
            headers=headers,
            params=params,
            body=body,
            timeout_seconds=timeout_seconds,
        )
        if error:
            return candidates, error
        items = _path(response, items_path)
        if not isinstance(items, list):
            return candidates, "invalid_api_items"
        for value in items:
            if not isinstance(value, Mapping):
                continue
            article_id = _text(value, str(mapping.get("id", "")))
            title = _text(value, str(mapping.get("title", "")))
            item_url = _text(value, str(mapping.get("url", "")))
            if not article_id or not title or not item_url:
                continue
            absolute_url = urljoin(url, item_url)
            canonical_url = canonicalize_url(absolute_url)
            candidates.append(
                SourceCandidate(
                    source_id=source_id,
                    external_id=article_id,
                    url=absolute_url,
                    canonical_url=canonical_url,
                    title=title,
                    excerpt=_text(value, str(mapping.get("summary", ""))),
                    body=_text(value, str(mapping.get("content", ""))),
                    author=_text(value, str(mapping.get("author", ""))),
                    language=_text(value, str(mapping.get("language", ""))) or "en",
                    published_at=_date(
                        _text(value, str(mapping.get("published_at", ""))), fetched_at
                    ),
                    fetched_at=fetched_at,
                    raw={"adapter": "api", "id": article_id},
                )
            )
        if not pagination:
            break
        next_url = _path(response, str(next_path)) if isinstance(next_path, str) else None
        if isinstance(next_url, str) and next_url:
            url = urljoin(url, next_url)
        elif len(items) == 0:
            break
        else:
            page += 1
    return candidates, None
