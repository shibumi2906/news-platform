from __future__ import annotations

import httpx
from source_worker.fetcher import fetch_feed


async def test_fetch_feed_returns_ok_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<rss></rss>", headers={"ETag": "abc123"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch_feed(
        client, "https://example.com/feed.xml", user_agent="test-agent", timeout_seconds=5.0
    )
    await client.aclose()

    assert result.status == "ok"
    assert result.body == b"<rss></rss>"
    assert result.etag == "abc123"


async def test_fetch_feed_returns_not_modified_on_304() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-None-Match"] == "abc123"
        return httpx.Response(304)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch_feed(
        client,
        "https://example.com/feed.xml",
        user_agent="test-agent",
        timeout_seconds=5.0,
        etag="abc123",
    )
    await client.aclose()

    assert result.status == "not_modified"
    assert result.body is None


async def test_fetch_feed_retries_on_429_then_succeeds() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, content=b"<rss></rss>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch_feed(
        client, "https://example.com/feed.xml", user_agent="test-agent", timeout_seconds=5.0
    )
    await client.aclose()

    assert result.status == "ok"
    assert attempts["count"] == 2


async def test_fetch_feed_gives_up_after_max_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"Retry-After": "0"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch_feed(
        client,
        "https://example.com/feed.xml",
        user_agent="test-agent",
        timeout_seconds=5.0,
        max_attempts=2,
    )
    await client.aclose()

    assert result.status == "error"
    assert result.error == "http_503"


async def test_fetch_feed_returns_error_on_permanent_4xx_without_retry() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch_feed(
        client, "https://example.com/feed.xml", user_agent="test-agent", timeout_seconds=5.0
    )
    await client.aclose()

    assert result.status == "error"
    assert result.error == "http_404"
    assert attempts["count"] == 1


async def test_fetch_feed_redacts_transport_exception_details() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private-source-credential", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch_feed(
        client,
        "https://user:private-source-credential@example.com/feed.xml",
        user_agent="test-agent",
        timeout_seconds=5.0,
        max_attempts=1,
    )
    await client.aclose()

    assert result.error == "transport_connecterror"
    assert "private-source-credential" not in result.error
