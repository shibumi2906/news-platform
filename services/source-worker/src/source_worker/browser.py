"""Playwright-driven, configuration-only browser source connector."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin
from uuid import UUID

from contracts.source import SourceCandidate

from source_worker.rss import canonicalize_url


def _date(value: str | None, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return fallback


def _number(config: Mapping[str, object], key: str, default: int) -> int:
    try:
        return max(1, int(str(config.get(key, default))))
    except (TypeError, ValueError):
        return default


def _transient_browser_error(error: Exception) -> bool:
    message = str(error).lower()
    return type(error).__name__ == "TimeoutError" or any(
        marker in message
        for marker in ("timeout", "net::", "connection", "temporarily unavailable")
    )


async def _navigate(page: Any, url: str, *, wait_until: str, timeout: float, retries: int) -> None:
    for attempt in range(retries + 1):
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            return
        except Exception as exc:
            if attempt == retries or not _transient_browser_error(exc):
                raise
            await asyncio.sleep(0.1 * (2**attempt))


async def _optional_text(page: Any, selector: object) -> str | None:
    if not isinstance(selector, str) or not selector:
        return None
    try:
        value = await page.locator(selector).inner_text()
        return value.strip() or None
    except Exception:
        return None


async def collect_browser_source(
    browser: Any,
    *,
    source_id: UUID,
    start_url: str,
    config: Mapping[str, object],
    fetched_at: datetime,
    user_agent: str,
    max_concurrency: int = 3,
) -> tuple[list[SourceCandidate], str | None]:
    """Render configured listing and article pages without leaking browser resources."""
    timeout = float(_number(config, "navigation_timeout_ms", 30_000))
    wait_until = str(config.get("wait_until", "networkidle"))
    retries = _number(config, "navigation_retries", 2) - 1
    concurrency = min(max_concurrency, _number(config, "max_concurrency", max_concurrency))
    context = await browser.new_context(user_agent=str(config.get("user_agent", user_agent)))
    page = await context.new_page()
    try:
        links: list[tuple[str, str]] = []
        list_url = start_url
        visited_list_urls: set[str] = set()
        for _ in range(_number(config, "max_pages", 1)):
            if list_url in visited_list_urls:
                break
            visited_list_urls.add(list_url)
            await _navigate(page, list_url, wait_until=wait_until, timeout=timeout, retries=retries)
            wait_selector = config.get("wait_selector")
            if isinstance(wait_selector, str) and wait_selector:
                await page.wait_for_selector(wait_selector, timeout=timeout)
            cards = page.locator(str(config["item_selector"]))
            for index in range(await cards.count()):
                try:
                    card = cards.nth(index)
                    title = await card.locator(str(config["title_selector"])).inner_text()
                    href = await card.locator(str(config["url_selector"])).get_attribute("href")
                    if title and href:
                        links.append((title.strip(), urljoin(list_url, href)))
                except Exception:
                    continue
            next_selector = config.get("next_selector")
            if not isinstance(next_selector, str) or not next_selector:
                break
            next_href = await page.locator(next_selector).get_attribute("href")
            if not next_href:
                break
            list_url = urljoin(list_url, next_href)

        semaphore = asyncio.Semaphore(concurrency)

        async def article(title: str, url: str) -> SourceCandidate | None:
            async with semaphore:
                child = await context.new_page()
                try:
                    await _navigate(
                        child, url, wait_until=wait_until, timeout=timeout, retries=retries
                    )
                    canonical = await child.locator(
                        str(config.get("canonical_selector", "link[rel=canonical]"))
                    ).get_attribute("href")
                    content = await _optional_text(child, config.get("content_selector"))
                    if not content:
                        return None
                    canonical_url = canonicalize_url(urljoin(url, canonical or url))
                    return SourceCandidate(
                        source_id=source_id,
                        external_id=hashlib.sha256(canonical_url.encode()).hexdigest(),
                        url=url,
                        canonical_url=canonical_url,
                        title=title,
                        body=content,
                        author=await _optional_text(child, config.get("author_selector")),
                        language=(await _optional_text(child, config.get("language_selector")))
                        or str(config.get("language", "en")),
                        published_at=_date(
                            await _optional_text(child, config.get("published_at_selector")),
                            fetched_at,
                        ),
                        fetched_at=fetched_at,
                        raw={"adapter": "playwright"},
                    )
                except Exception:
                    return None
                finally:
                    await child.close()

        results = await asyncio.gather(*(article(*link) for link in links))
        return [item for item in results if item], None
    except Exception as exc:
        return [], f"browser_{type(exc).__name__.lower()}"
    finally:
        await page.close()
        await context.close()
