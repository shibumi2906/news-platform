"""RSS/Atom adapter: `fetch bytes -> normalize` half of docs/05 §1's
`discover -> fetch -> normalize -> checkpoint` pipeline.

Per docs/05 §2 the adapter only produces `SourceCandidate` values — it never
creates an `Event` or writes an article; that happens in `ingestion.py`.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime
from time import struct_time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import feedparser
from contracts.source import SourceCandidate


def canonicalize_url(url: str) -> str:
    """Strip fragment and query string so tracking parameters don't defeat
    dedup — two entries that only differ by `?utm_source=...` are the same
    material."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _struct_time_to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


def _json_safe(value: Any) -> Any:
    """Recursively strip feedparser's non-JSON-serializable values (notably
    `time.struct_time`) so `raw` can be persisted in a JSON/JSONB column."""
    if isinstance(value, struct_time):
        return _struct_time_to_datetime(value).isoformat()  # type: ignore[union-attr]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def parse_rss_feed(
    raw: bytes, *, source_id: UUID, fetched_at: datetime, default_language: str = "en"
) -> list[SourceCandidate]:
    """Parse raw RSS/Atom bytes into `SourceCandidate` values. Entries without
    a usable link or a stable external ID are skipped rather than raising —
    a single malformed entry must not fail the whole poll."""
    parsed = feedparser.parse(raw)
    feed_language = parsed.feed.get("language") or default_language

    candidates: list[SourceCandidate] = []
    for entry in parsed.entries:
        url = entry.get("link")
        if not url:
            continue
        external_id = entry.get("id") or entry.get("guid") or url

        published_at = _struct_time_to_datetime(entry.get("published_parsed"))
        updated_at = _struct_time_to_datetime(entry.get("updated_parsed"))
        if published_at is None:
            published_at = updated_at or fetched_at

        author = entry.get("author")
        excerpt = entry.get("summary")
        body = None
        content_entries = entry.get("content")
        if content_entries:
            body = content_entries[0].get("value")

        candidates.append(
            SourceCandidate(
                source_id=source_id,
                external_id=external_id,
                url=url,
                canonical_url=canonicalize_url(url),
                title=entry.get("title") or "",
                excerpt=excerpt,
                body=body,
                author=author,
                language=feed_language,
                published_at=published_at,
                updated_at=updated_at,
                fetched_at=fetched_at,
                raw=_json_safe(dict(entry)),
            )
        )
    return candidates
