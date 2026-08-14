"""Google Programmable Search and Gemini Google Search source connectors."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

import httpx
from contracts.source import SourceCandidate

from source_worker.api import _request_json
from source_worker.rss import canonicalize_url

_GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
_GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(config: Mapping[str, object], key: str, default: int) -> int:
    try:
        return int(str(config.get(key, default)))
    except (TypeError, ValueError):
        return default


def _date(value: object, fallback: datetime) -> datetime:
    if not isinstance(value, str):
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return fallback


def _secret(config: Mapping[str, object], error: str) -> tuple[str | None, str | None]:
    env_name = _text(config.get("api_key_env"))
    secret = os.getenv(env_name) if env_name else None
    return (secret, None) if secret else (None, error)


def _publication_date(item: Mapping[str, object]) -> object:
    metatags = _mapping(item.get("pagemap")).get("metatags")
    # Google returns a list of meta-tag maps; only consume well-known, optional fields.
    if isinstance(metatags, list):
        tags = _mapping(metatags[0]) if metatags else {}
    else:
        tags = _mapping(metatags)
    return tags.get("article:published_time") or tags.get("datePublished") or tags.get("date")


def _candidate(
    *,
    source_id: UUID,
    url: str,
    title: str,
    snippet: str | None,
    published_at: datetime,
    fetched_at: datetime,
    language: str,
    raw: dict[str, object],
) -> SourceCandidate:
    canonical_url = canonicalize_url(url)
    return SourceCandidate(
        source_id=source_id,
        external_id=canonical_url,
        url=url,
        canonical_url=canonical_url,
        title=title,
        excerpt=snippet,
        body=snippet,
        language=language,
        published_at=published_at,
        fetched_at=fetched_at,
        raw=raw,
    )


async def collect_google_search_source(
    client: httpx.AsyncClient,
    *,
    source_id: UUID,
    config: Mapping[str, object],
    fetched_at: datetime,
    user_agent: str,
    timeout_seconds: float,
) -> tuple[list[SourceCandidate], str | None]:
    """Collect configurable Google Programmable Search results."""
    api_key, error = _secret(config, "missing_google_search_api_key")
    if error or not api_key:
        return [], error
    query = _text(config.get("query"))
    engine_id = _text(config.get("search_engine_id"))
    if not query or not engine_id:
        return [], "invalid_google_search_config"
    language = _text(config.get("language")) or "en"
    page_size = min(10, max(1, _number(config, "page_size", 10)))
    limit = max(1, _number(config, "limit", page_size))
    max_pages = max(1, _number(config, "max_pages", (limit + page_size - 1) // page_size))
    params = {"key": api_key, "cx": engine_id, "q": query, "num": str(page_size)}
    if locale := _text(config.get("locale")):
        params["hl"] = locale
    if region := _text(config.get("region")):
        params["gl"] = region
    if language:
        params["lr"] = f"lang_{language}"
    url = str(config.get("endpoint_url", _GOOGLE_SEARCH_URL))
    candidates: list[SourceCandidate] = []
    seen: set[str] = set()
    for page in range(max_pages):
        response, error = await _request_json(
            client,
            url=url,
            method="GET",
            headers={"User-Agent": user_agent},
            params={**params, "start": str(1 + page * page_size)},
            body=None,
            timeout_seconds=timeout_seconds,
        )
        if error:
            return candidates, error
        items = _mapping(response).get("items")
        if items is None:
            break
        if not isinstance(items, list):
            return candidates, "invalid_google_search_response"
        for item in items:
            if not isinstance(item, Mapping):
                continue
            result_url = _text(item.get("link"))
            title = _text(item.get("title"))
            if not result_url or not title:
                continue
            canonical_url = canonicalize_url(result_url)
            if canonical_url in seen:
                continue
            seen.add(canonical_url)
            candidates.append(
                _candidate(
                    source_id=source_id,
                    url=result_url,
                    title=title,
                    snippet=_text(item.get("snippet")),
                    published_at=_date(_publication_date(item), fetched_at),
                    fetched_at=fetched_at,
                    language=language,
                    raw={"adapter": "google_search", "result": dict(item)},
                )
            )
            if len(candidates) >= limit:
                return candidates, None
        if len(items) < page_size:
            break
    return candidates, None


async def collect_gemini_search_source(
    client: httpx.AsyncClient,
    *,
    source_id: UUID,
    config: Mapping[str, object],
    fetched_at: datetime,
    user_agent: str,
    timeout_seconds: float,
) -> tuple[list[SourceCandidate], str | None]:
    """Use Gemini Google Search grounding and ingest its cited web sources."""
    api_key, error = _secret(config, "missing_gemini_api_key")
    if error or not api_key:
        return [], error
    query = _text(config.get("query"))
    if not query:
        return [], "invalid_gemini_search_config"
    language = _text(config.get("language")) or "en"
    locale = _text(config.get("locale"))
    region = _text(config.get("region"))
    prompt = query
    if locale or region or language:
        prompt = f"{query}\nSearch locale: {locale or language}; region: {region or 'global'}."
    model = _text(config.get("model")) or "gemini-2.5-flash"
    api_root = str(config.get("api_root", _GEMINI_API_ROOT)).rstrip("/")
    response, error = await _request_json(
        client,
        url=f"{api_root}/models/{model}:generateContent",
        method="POST",
        headers={"User-Agent": user_agent, "x-goog-api-key": api_key},
        params={},
        body={
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        },
        timeout_seconds=timeout_seconds,
    )
    if error:
        return [], error
    candidates = _mapping(response).get("candidates")
    if candidates is None:
        return [], None
    if not isinstance(candidates, list):
        return [], "invalid_gemini_search_response"
    result: list[SourceCandidate] = []
    seen: set[str] = set()
    limit = max(1, _number(config, "limit", 10))
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        content = _mapping(candidate.get("content"))
        parts = content.get("parts")
        summary = (
            "\n".join(
                text
                for part in parts
                if isinstance(part, Mapping)
                if (text := _text(part.get("text")))
            )
            if isinstance(parts, list)
            else None
        )
        metadata = _mapping(candidate.get("groundingMetadata"))
        chunks = metadata.get("groundingChunks")
        if not isinstance(chunks, list):
            continue
        for chunk in chunks:
            web = _mapping(_mapping(chunk).get("web"))
            result_url = _text(web.get("uri"))
            title = _text(web.get("title"))
            if not result_url or not title:
                continue
            canonical_url = canonicalize_url(result_url)
            if canonical_url in seen:
                continue
            seen.add(canonical_url)
            result.append(
                _candidate(
                    source_id=source_id,
                    url=result_url,
                    title=title,
                    snippet=summary,
                    published_at=fetched_at,
                    fetched_at=fetched_at,
                    language=language,
                    raw={"adapter": "gemini_search", "grounding": dict(web)},
                )
            )
            if len(result) >= limit:
                return result, None
    return result, None
