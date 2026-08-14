from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from source_worker.browser import collect_browser_source


class FakeLocator:
    def __init__(self, value: object = None) -> None:
        self.value = value

    async def count(self) -> int:
        return len(self.value) if isinstance(self.value, list) else 0

    def nth(self, index: int) -> FakeLocator:
        if isinstance(self.value, list):
            return FakeLocator(self.value[index])
        return FakeLocator()

    def locator(self, selector: str) -> FakeLocator:
        if isinstance(self.value, dict):
            return FakeLocator(self.value.get(selector))
        return FakeLocator()

    async def inner_text(self) -> str:
        if isinstance(self.value, Exception):
            raise self.value
        return str(self.value or "")

    async def get_attribute(self, name: str) -> str | None:
        if isinstance(self.value, Exception):
            raise self.value
        return self.value if isinstance(self.value, str) else None


class FakePage:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.data: dict[str, object] = {}
        self.closed = False

    async def goto(self, url: str, *, wait_until: str, timeout: float) -> None:
        response = self.context.pages_data[url]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, tuple):
            await asyncio.sleep(response[0])
            response = response[1]
        self.data = response  # type: ignore[assignment]

    async def wait_for_selector(self, selector: str, *, timeout: float) -> None:
        if selector not in self.data:
            raise TimeoutError(selector)

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self.data.get(selector))

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.context.open_pages -= 1


class FakeContext:
    def __init__(self, pages_data: dict[str, object]) -> None:
        self.pages_data = pages_data
        self.pages: list[FakePage] = []
        self.open_pages = 0
        self.peak_open_pages = 0
        self.closed = False

    async def new_page(self) -> FakePage:
        page = FakePage(self)
        self.pages.append(page)
        self.open_pages += 1
        self.peak_open_pages = max(self.peak_open_pages, self.open_pages)
        return page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, pages_data: dict[str, object]) -> None:
        self.context = FakeContext(pages_data)

    async def new_context(self, *, user_agent: str) -> FakeContext:
        return self.context


def config(**extra: object) -> dict[str, object]:
    return {
        "item_selector": ".card",
        "title_selector": ".title",
        "url_selector": "a",
        "content_selector": ".body",
        **extra,
    }


@pytest.mark.asyncio
async def test_browser_connector_extracts_rendered_article_relative_and_canonical_url() -> None:
    browser = FakeBrowser(
        {
            "https://news.test/list": {".card": [{".title": "Rendered", "a": "/article"}]},
            "https://news.test/article": {
                ".body": "Client rendered content",
                "link[rel=canonical]": "/canonical?utm_source=x",
                ".author": "Author",
                ".date": "2025-01-02T03:04:05Z",
            },
        }
    )
    candidates, error = await collect_browser_source(
        browser,
        source_id=uuid4(),
        start_url="https://news.test/list",
        config=config(author_selector=".author", published_at_selector=".date"),
        fetched_at=datetime.now(UTC),
        user_agent="test",
    )
    assert error is None
    assert candidates[0].url == "https://news.test/article"
    assert candidates[0].canonical_url == "https://news.test/canonical"
    assert candidates[0].body == "Client rendered content"
    assert candidates[0].author == "Author"


@pytest.mark.asyncio
async def test_browser_connector_handles_optional_fields_malformed_article_and_timeout() -> None:
    browser = FakeBrowser(
        {
            "https://news.test/list": {
                ".card": [{".title": "Good", "a": "/good"}, {".title": "Bad", "a": "/bad"}]
            },
            "https://news.test/good": {
                ".body": "Only required fields",
                "link[rel=canonical]": None,
            },
            "https://news.test/bad": TimeoutError("navigation timeout"),
        }
    )
    candidates, error = await collect_browser_source(
        browser,
        source_id=uuid4(),
        start_url="https://news.test/list",
        config=config(navigation_retries=1),
        fetched_at=datetime.now(UTC),
        user_agent="test",
    )
    assert error is None
    assert len(candidates) == 1
    assert candidates[0].author is None
    assert candidates[0].language == "en"


@pytest.mark.asyncio
async def test_browser_connector_paginates_deduplicates_by_canonical_and_closes_pages() -> None:
    browser = FakeBrowser(
        {
            "https://news.test/list": {
                ".card": [{".title": "A", "a": "/a"}],
                ".next": "/list?page=2",
            },
            "https://news.test/list?page=2": {".card": [{".title": "A again", "a": "/a-copy"}]},
            "https://news.test/a": {".body": "A", "link[rel=canonical]": "/a"},
            "https://news.test/a-copy": {".body": "A", "link[rel=canonical]": "/a"},
        }
    )
    candidates, error = await collect_browser_source(
        browser,
        source_id=uuid4(),
        start_url="https://news.test/list",
        config=config(next_selector=".next", max_pages=2),
        fetched_at=datetime.now(UTC),
        user_agent="test",
    )
    assert error is None
    assert len(candidates) == 2
    assert candidates[0].external_id == candidates[1].external_id
    assert all(page.closed for page in browser.context.pages)
    assert browser.context.closed


@pytest.mark.asyncio
async def test_browser_connector_retries_transient_list_error_and_bounds_article_concurrency() -> (
    None
):
    class RetryPage(FakePage):
        async def goto(self, url: str, *, wait_until: str, timeout: float) -> None:
            if url == "https://news.test/list" and not getattr(self, "retried", False):
                self.retried = True
                raise TimeoutError("temporary timeout")
            await super().goto(url, wait_until=wait_until, timeout=timeout)

    class RetryContext(FakeContext):
        async def new_page(self) -> FakePage:
            page = RetryPage(self)
            self.pages.append(page)
            self.open_pages += 1
            self.peak_open_pages = max(self.peak_open_pages, self.open_pages)
            return page

    browser = FakeBrowser({})
    browser.context = RetryContext(
        {
            "https://news.test/list": {
                ".card": [{".title": str(i), "a": f"/{i}"} for i in range(4)]
            },
            **{
                f"https://news.test/{i}": (0.01, {".body": str(i), "link[rel=canonical]": None})
                for i in range(4)
            },
        }
    )
    candidates, error = await collect_browser_source(
        browser,
        source_id=uuid4(),
        start_url="https://news.test/list",
        config=config(max_concurrency=2),
        fetched_at=datetime.now(UTC),
        user_agent="test",
    )
    assert error is None
    assert len(candidates) == 4
    # Listing page plus at most two article pages may be open simultaneously.
    assert browser.context.peak_open_pages <= 3
