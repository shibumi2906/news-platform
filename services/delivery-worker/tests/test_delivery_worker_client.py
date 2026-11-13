from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
from common.logging import bind_correlation_id, reset_correlation_id
from common.signing import (
    CONNECTION_ID_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    SIGNATURE_HEADER,
    SIGNING_KEY_ID_HEADER,
    verify,
)
from contracts.package import CanonicalNewsPackageEnvelope, PackageContent, PackageSourceRef
from delivery_worker.client import send_package


async def test_send_package_signs_request_and_returns_delivered_on_200() -> None:
    captured: dict[str, httpx.Request] = {}
    connection_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(202)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    correlation_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    context_token = bind_correlation_id(correlation_id)
    try:
        result = await send_package(
            client,
            connection_id=connection_id,
            delivery_url="https://site.example.com",
            hmac_secret="s3cret",
            idempotency_key="pkg-1:1",
            body=b'{"package_id": "pkg-1"}',
            timeout_seconds=5.0,
        )
    finally:
        reset_correlation_id(context_token)
    await client.aclose()

    assert result.status == "delivered"
    assert result.response_status_code == 202

    request = captured["request"]
    assert request.url == "https://site.example.com/api/v1/incoming-news-packages"
    assert request.headers[IDEMPOTENCY_KEY_HEADER] == "pkg-1:1"
    assert request.headers[CONNECTION_ID_HEADER] == str(connection_id)
    assert request.headers[SIGNING_KEY_ID_HEADER] == "legacy"
    assert request.headers["X-Request-Id"] == correlation_id
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


async def test_send_package_redacts_transport_exception_details() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private-url-value", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await send_package(
        client,
        connection_id=uuid4(),
        delivery_url="https://user:private-url-value@site.example.com",
        hmac_secret="s3cret",
        idempotency_key="pkg-1:1",
        body=b"{}",
        timeout_seconds=5.0,
        max_attempts=1,
    )
    await client.aclose()

    assert result.status == "failed"
    assert result.error == "transport_connecterror"
    assert "private-url-value" not in result.error


async def test_send_package_rejects_inconsistent_nonempty_acknowledgement() -> None:
    now = datetime.now(UTC)
    envelope = CanonicalNewsPackageEnvelope(
        package_id=uuid4(),
        package_version=1,
        instance_id=uuid4(),
        event_id=uuid4(),
        content=PackageContent(
            title="Title", canonical_url="https://example.test/one", language="en"
        ),
        sources=[
            PackageSourceRef(
                source_id=uuid4(),
                source_material_id=uuid4(),
                external_id="one",
                url="https://example.test/one",
                published_at=now,
                fetched_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "package_id": str(uuid4()),
                "package_version": 99,
                "status": "accepted",
                "received_at": "2026-08-26T12:00:00Z",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await send_package(
        client,
        connection_id=uuid4(),
        delivery_url="https://site.example.com",
        hmac_secret="s3cret",
        idempotency_key="pkg-1:1",
        body=envelope.model_dump_json().encode(),
        timeout_seconds=5.0,
    )
    await client.aclose()
    assert result.status == "failed"
    assert result.error == "inconsistent_acknowledgement"
