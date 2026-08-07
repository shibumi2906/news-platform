"""Conservative baseline HTML adapter; richer parsers stay isolated extensions."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from contracts.source import SourceCandidate

from source_worker.rss import canonicalize_url

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_BODY = re.compile(r"<body[^>]*>(.*?)</body>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")


def parse_html_document(
    raw: bytes, *, source_id: UUID, url: str, fetched_at: datetime
) -> list[SourceCandidate]:
    text = raw.decode("utf-8", errors="replace")
    title = _TITLE.search(text)
    body = _BODY.search(text)
    return [
        SourceCandidate(
            source_id=source_id,
            external_id=canonicalize_url(url),
            url=url,
            canonical_url=canonicalize_url(url),
            title=_TAGS.sub("", title.group(1)).strip() if title else "",
            body=_TAGS.sub(" ", body.group(1)).strip() if body else None,
            language="en",
            published_at=fetched_at,
            fetched_at=fetched_at,
            raw={"adapter": "html"},
        )
    ]
