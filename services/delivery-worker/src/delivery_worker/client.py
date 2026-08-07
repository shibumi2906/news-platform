"""Signed delivery to a Site instance's ingestion endpoint (ADR-003).

docs/05 §3's HTTP discipline (timeout, `Retry-After`, bounded retry) applies
here too, mirrored from `source_worker.fetcher.fetch_feed`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import httpx
from common.ids import new_uuid_str
from common.logging import get_correlation_id
from common.signing import (
    CONNECTION_ID_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    NONCE_HEADER,
    SIGNATURE_HEADER,
    SIGNATURE_VERSION,
    SIGNATURE_VERSION_HEADER,
    TIMESTAMP_HEADER,
    sign,
)
from common.time import to_iso8601, utc_now

#: docs/02 §9: `Site Ingestion API   /api/v1/incoming-news-packages`.
#: `SiteConnection.delivery_url` is the site instance's base URL.
INCOMING_PACKAGES_PATH = "/api/v1/incoming-news-packages"

DeliveryStatus = Literal["delivered", "failed"]

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_DEFAULT_RETRY_AFTER_SECONDS = 1.0


@dataclass(frozen=True)
class DeliveryResult:
    status: DeliveryStatus
    response_status_code: int | None = None
    error: str | None = None


async def send_package(
    client: httpx.AsyncClient,
    *,
    connection_id: UUID,
    delivery_url: str,
    hmac_secret: str,
    idempotency_key: str,
    body: bytes,
    timeout_seconds: float,
    max_attempts: int = 3,
) -> DeliveryResult:
    url = delivery_url.rstrip("/") + INCOMING_PACKAGES_PATH
    timestamp = to_iso8601(utc_now())
    nonce = new_uuid_str()
    signature = sign(
        hmac_secret, timestamp=timestamp, nonce=nonce, idempotency_key=idempotency_key, body=body
    )
    headers = {
        "Content-Type": "application/json",
        CONNECTION_ID_HEADER: str(connection_id),
        SIGNATURE_VERSION_HEADER: SIGNATURE_VERSION,
        SIGNATURE_HEADER: signature,
        TIMESTAMP_HEADER: timestamp,
        NONCE_HEADER: nonce,
        IDEMPOTENCY_KEY_HEADER: idempotency_key,
    }
    correlation_id = get_correlation_id()
    if correlation_id is not None:
        headers["X-Request-Id"] = correlation_id

    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = await client.post(
                url, content=body, headers=headers, timeout=timeout_seconds
            )
        except httpx.HTTPError as exc:
            last_error = f"transport_{type(exc).__name__.lower()}"
            if attempt < max_attempts:
                await asyncio.sleep(_DEFAULT_RETRY_AFTER_SECONDS)
                continue
            return DeliveryResult(status="failed", error=last_error)

        if response.status_code in (200, 201, 202):
            return DeliveryResult(status="delivered", response_status_code=response.status_code)

        if response.status_code in _RETRYABLE_STATUS_CODES:
            last_error = f"http_{response.status_code}"
            if attempt < max_attempts:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                await asyncio.sleep(retry_after)
                continue
            return DeliveryResult(
                status="failed", response_status_code=response.status_code, error=last_error
            )

        return DeliveryResult(
            status="failed",
            response_status_code=response.status_code,
            error=f"http_{response.status_code}",
        )

    return DeliveryResult(status="failed", error=last_error or "unknown_error")


def _parse_retry_after(value: str | None) -> float:
    if value is None:
        return _DEFAULT_RETRY_AFTER_SECONDS
    try:
        return max(float(value), 0.0)
    except ValueError:
        return _DEFAULT_RETRY_AFTER_SECONDS
