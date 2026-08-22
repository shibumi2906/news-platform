"""HTTP fetch step of docs/05 §1's `discover -> fetch -> normalize ->
checkpoint` pipeline.

docs/05 §3: HTTP uses a timeout, conditional requests, `Retry-After` and a
bounded retry — never an unbounded retry loop.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import httpx

FetchStatus = Literal["ok", "not_modified", "error"]

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_DEFAULT_RETRY_AFTER_SECONDS = 1.0


@dataclass(frozen=True)
class FetchResult:
    status: FetchStatus
    body: bytes | None = None
    etag: str | None = None
    last_modified: str | None = None
    error: str | None = None


async def fetch_feed(
    client: httpx.AsyncClient,
    url: str,
    *,
    user_agent: str,
    timeout_seconds: float,
    etag: str | None = None,
    last_modified: str | None = None,
    max_attempts: int = 3,
) -> FetchResult:
    headers = {"User-Agent": user_agent}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = await client.get(url, headers=headers, timeout=timeout_seconds)
        except httpx.HTTPError as exc:
            last_error = str(exc)
            if attempt < max_attempts:
                await asyncio.sleep(_DEFAULT_RETRY_AFTER_SECONDS)
                continue
            return FetchResult(status="error", error=last_error)

        if response.status_code == 304:
            return FetchResult(status="not_modified")

        if response.status_code in _RETRYABLE_STATUS_CODES:
            last_error = f"http_{response.status_code}"
            if attempt < max_attempts:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                await asyncio.sleep(retry_after)
                continue
            return FetchResult(status="error", error=last_error)

        if response.status_code >= 400:
            return FetchResult(status="error", error=f"http_{response.status_code}")

        return FetchResult(
            status="ok",
            body=response.content,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )

    return FetchResult(status="error", error=last_error or "unknown_error")


def _parse_retry_after(value: str | None) -> float:
    if value is None:
        return _DEFAULT_RETRY_AFTER_SECONDS
    try:
        return max(float(value), 0.0)
    except ValueError:
        return _DEFAULT_RETRY_AFTER_SECONDS
