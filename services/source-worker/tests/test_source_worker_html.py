from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
from source_worker.html import collect_html_source

LISTING = b"""
<main><article class='story'><a class='headline' href='/news/one'>First headline</a></article>
<article class='story'><a class='headline' href='/news/two'>Second headline</a></article></main>
"""
ARTICLE = b"""
<html><head><link rel='canonical' href='/canonical/one?utm=x'>
<meta property='og:image' content='/images/one.jpg'></head>
<body><main class='article-body'>The complete article text.</main>
<time class='published' datetime='2026-08-10T12:00:00Z'></time>
<span class='byline'>Jane</span></body></html>
"""


def _config(**overrides: object) -> dict[str, object]:
    return {
        "item_selector": "article.story",
        "url_selector": "a.headline",
        "title_selector": "a.headline",
        "content_selector": "main.article-body",
        "published_at_selector": "time.published",
        "author_selector": "span.byline",
        "language": "en",
        **overrides,
    }


async def test_html_connector_extracts_normal_page_relative_urls_and_canonical() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/news":
            assert request.headers["User-Agent"] == "html-test-agent"
            return httpx.Response(200, content=LISTING)
        return httpx.Response(200, content=ARTICLE)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        candidates, _, _, error = await collect_html_source(
            client,
            source_id=uuid4(),
            list_url="https://example.test/news",
            config=_config(),
            fetched_at=datetime(2026, 8, 11, tzinfo=UTC),
            user_agent="html-test-agent",
            timeout_seconds=1,
        )
    assert error is None
    assert len(candidates) == 2
    first = candidates[0]
    assert first.url == "https://example.test/news/one"
    assert first.canonical_url == "https://example.test/canonical/one"
    assert first.title == "First headline"
    assert first.body == "The complete article text."
    assert first.author == "Jane"
    assert first.published_at == datetime(2026, 8, 10, 12, tzinfo=UTC)
    assert first.raw["media"] == [
        {
            "type": "image",
            "source_url": "https://example.test/images/one.jpg",
            "provider": "source",
        }
    ]


async def test_html_connector_tolerates_malformed_html_and_missing_optional_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/news":
            return httpx.Response(
                200, content=b"<article class=story><a class=headline href=/one>Title"
            )
        return httpx.Response(200, content=b"<main class=article-body>Body without closing tags")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, _, _, error = await collect_html_source(
            client,
            source_id=uuid4(),
            list_url="https://example.test/news",
            config=_config(),
            fetched_at=datetime(2026, 8, 11, tzinfo=UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None
    assert len(candidates) == 1
    assert candidates[0].author is None
    assert candidates[0].published_at == datetime(2026, 8, 11, tzinfo=UTC)


async def test_html_connector_reports_timeout_and_skips_unavailable_article() -> None:
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as client:
        candidates, _, _, error = await collect_html_source(
            client,
            source_id=uuid4(),
            list_url="https://example.test/news",
            config=_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=0.01,
        )
    assert candidates == []
    assert error == "transport_readtimeout"


async def test_html_connector_supports_different_source_rules() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed":
            return httpx.Response(
                200, content=b"<section data-card><a data-link href='/post'>Different</a>"
            )
        return httpx.Response(200, content=b"<div data-content>Other text</div>")

    config = {
        "item_selector": "section[data-card]",
        "url_selector": "a[data-link]",
        "title_selector": "a[data-link]",
        "content_selector": "div[data-content]",
        "language": "fr",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, _, _, error = await collect_html_source(
            client,
            source_id=uuid4(),
            list_url="https://example.test/feed",
            config=config,
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None
    assert candidates[0].language == "fr"
    assert candidates[0].body == "Other text"
