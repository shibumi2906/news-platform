"""Configuration-driven HTML connector without browser automation."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin
from uuid import UUID

import httpx
from contracts.source import SourceCandidate

from source_worker.fetcher import fetch_feed
from source_worker.rss import canonicalize_url


class Node:
    def __init__(self, tag: str, attrs: dict[str, str], parent: Node | None) -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[Node] = []
        self.text_parts: list[str] = []

    def text(self) -> str:
        return " ".join([*self.text_parts, *(child.text() for child in self.children)]).strip()


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {}, None)
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key.lower(): value or "" for key, value in attrs}, self.current)
        self.current.children.append(node)
        if tag.lower() not in {"meta", "link", "img", "br", "hr", "input"}:
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        cursor: Node | None = self.current
        while cursor is not None and cursor.tag != tag.lower():
            cursor = cursor.parent
        if cursor is not None and cursor.parent is not None:
            self.current = cursor.parent

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.current.text_parts.append(data.strip())


def _matches(node: Node, term: str) -> bool:
    match = re.fullmatch(
        r"(?:(?P<tag>[\w-]+)|)(?P<id>#[\w-]+|)(?P<class>(?:\.[\w-]+)*)(?P<attr>\[[^\]]+\]|)",
        term,
    )
    if match is None:
        return False
    tag, node_id, classes, attr = match.group("tag", "id", "class", "attr")
    if tag and node.tag != tag:
        return False
    if node_id and node.attrs.get("id") != node_id[1:]:
        return False
    node_classes = set(node.attrs.get("class", "").split())
    if any(value not in node_classes for value in classes.split(".") if value):
        return False
    if attr:
        key, separator, value = attr[1:-1].partition("=")
        key, value = key.strip().lower(), value.strip().strip("\"'")
        if key not in node.attrs or (separator and node.attrs[key] != value):
            return False
    return True


def select(root: Node, selector: str) -> list[Node]:
    """Small safe selector subset: tag, .class, #id, [attr], descendant and comma."""
    matches: list[Node] = []
    for branch in selector.split(","):
        terms = [term for term in branch.strip().split() if term]
        if not terms:
            continue
        candidates = [root]
        for term in terms:
            next_candidates: list[Node] = []
            for candidate in candidates:
                next_candidates.extend(_descendants(candidate, term))
            candidates = next_candidates
        matches.extend(candidates)
    return list(dict.fromkeys(matches))


def _descendants(node: Node, term: str) -> list[Node]:
    result: list[Node] = []
    for child in node.children:
        if _matches(child, term):
            result.append(child)
        result.extend(_descendants(child, term))
    return result


def _first_text(root: Node, selector: str | None) -> str | None:
    if not selector:
        return None
    nodes = select(root, selector)
    return nodes[0].text() if nodes and nodes[0].text() else None


def _first_attr(root: Node, selector: str | None, attribute: str) -> str | None:
    if not selector:
        return None
    nodes = select(root, selector)
    return nodes[0].attrs.get(attribute) if nodes else None


def _parse_document(raw: bytes) -> DocumentParser:
    parser = DocumentParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    parser.close()
    return parser


def _published(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return fallback


def parse_html_document(
    raw: bytes, *, source_id: UUID, url: str, fetched_at: datetime
) -> list[SourceCandidate]:
    """Compatibility parser for previously stored bare HTML sources.

    New sources use :func:`collect_html_source` with explicit rules. This keeps
    migration/fixture compatibility without making it a site-specific parser.
    """
    page = _parse_document(raw)
    title = _first_text(page.root, "title") or ""
    body = _first_text(page.root, "body")
    if not title and not body:
        return []
    canonical_url = canonicalize_url(url)
    return [
        SourceCandidate(
            source_id=source_id,
            external_id=hashlib.sha256(canonical_url.encode()).hexdigest(),
            url=url,
            canonical_url=canonical_url,
            title=title,
            body=body,
            language="en",
            published_at=fetched_at,
            fetched_at=fetched_at,
            raw={"adapter": "html_legacy"},
        )
    ]


async def collect_html_source(
    client: httpx.AsyncClient,
    *,
    source_id: UUID,
    list_url: str,
    config: Mapping[str, object],
    fetched_at: datetime,
    user_agent: str,
    timeout_seconds: float,
) -> tuple[list[SourceCandidate], str | None, str | None, str | None]:
    """Fetch a listing and each configured article URL; malformed items are skipped."""
    listing = await fetch_feed(
        client, list_url, user_agent=user_agent, timeout_seconds=timeout_seconds
    )
    if listing.status != "ok" or listing.body is None:
        return [], listing.etag, listing.last_modified, listing.error
    document = _parse_document(listing.body)
    candidates: list[SourceCandidate] = []
    for item in select(document.root, str(config["item_selector"])):
        href = _first_attr(item, str(config["url_selector"]), "href")
        title = _first_text(item, str(config["title_selector"]))
        if not href or not title:
            continue
        url = urljoin(list_url, href)
        article = await fetch_feed(
            client, url, user_agent=user_agent, timeout_seconds=timeout_seconds
        )
        if article.status != "ok" or article.body is None:
            continue
        page = _parse_document(article.body)
        canonical = _first_attr(
            page.root, str(config.get("canonical_selector", "link[rel=canonical]")), "href"
        )
        canonical_url = canonicalize_url(urljoin(url, canonical or url))
        content = _first_text(page.root, str(config["content_selector"]))
        if not content:
            continue
        published_selector = config.get("published_at_selector")
        published = _first_attr(
            page.root,
            str(published_selector),
            str(config.get("published_at_attribute", "datetime")),
        )
        author = (
            _first_text(page.root, str(config["author_selector"]))
            if config.get("author_selector")
            else None
        )
        external_id = hashlib.sha256(canonical_url.encode()).hexdigest()
        image_selector = str(config.get("image_selector", "meta[property=og:image]"))
        image_url = _first_attr(
            page.root, image_selector, str(config.get("image_attribute", "content"))
        )
        media = (
            [{"type": "image", "source_url": urljoin(url, image_url), "provider": "source"}]
            if image_url
            else []
        )
        candidates.append(
            SourceCandidate(
                source_id=source_id,
                external_id=external_id,
                url=url,
                canonical_url=canonical_url,
                title=title,
                body=content,
                author=author,
                language=str(config.get("language", "en")),
                published_at=_published(published, fetched_at),
                fetched_at=fetched_at,
                raw={"adapter": "html", "list_url": list_url, "media": media},
            )
        )
    return candidates, listing.etag, listing.last_modified, None
