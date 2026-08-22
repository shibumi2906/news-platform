from __future__ import annotations

from uuid import uuid4

import httpx
from common.signing import CONNECTION_ID_HEADER, IDEMPOTENCY_KEY_HEADER, SIGNATURE_HEADER, verify
from delivery_worker.client import send_package


async def test_send_package_signs_request_and_returns_delivered_on_200() -> None:
    captured: dict[str, httpx.Request] = {}
    connection_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(202)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await send_package(
        client,
        connection_id=connection_id,
        delivery_url="https://site.example.com",
        hmac_secret="s3cret",
        idempotency_key="pkg-1:1",
        body=b'{"package_id": "pkg-1"}',
        timeout_seconds=5.0,
    )
    await client.aclose()

    assert result.status == "delivered"
    assert result.response_status_code == 202

    request = captured["request"]
    assert request.url == "https://site.example.com/api/v1/incoming-news-packages"
    assert request.headers[IDEMPOTENCY_KEY_HEADER] == "pkg-1:1"
    assert request.headers[CONNECTION_ID_HEADER] == str(connection_id)
    assert verify(
        "s3cret",
        timestamp=request.headers["X-Timestamp"],
        nonce=request.headers["X-Nonce"],
        idempotency_key="pkg-1:1",
        body=b'{"package_id": "pkg-1"}',
        signature=request.headers[SIGNATURE_HEADER],
    )


async def test_send_package_retries_on_503_then_succeeds() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await send_package(
        client,
        connection_id=uuid4(),
        delivery_url="https://site.example.com",
        hmac_secret="s3cret",
        idempotency_key="pkg-1:1",
        body=b"{}",
        timeout_seconds=5.0,
    )
    await client.aclose()

    assert result.status == "delivered"
    assert attempts["count"] == 2


async def test_send_package_gives_up_after_max_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, headers={"Retry-After": "0"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await send_package(
        client,
        connection_id=uuid4(),
        delivery_url="https://site.example.com",
        hmac_secret="s3cret",
        idempotency_key="pkg-1:1",
        body=b"{}",
        timeout_seconds=5.0,
        max_attempts=2,
    )
    await client.aclose()

    assert result.status == "failed"
    assert result.error == "http_500"


async def test_send_package_does_not_retry_permanent_4xx() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(422)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await send_package(
        client,
        connection_id=uuid4(),
        delivery_url="https://site.example.com",
        hmac_secret="s3cret",
        idempotency_key="pkg-1:1",
        body=b"{}",
        timeout_seconds=5.0,
    )
    await client.aclose()

    assert result.status == "failed"
    assert result.error == "http_422"
    assert attempts["count"] == 1
