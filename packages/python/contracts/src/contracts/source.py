"""Source connector adapter contract.

docs/05_SOURCE_CONNECTORS.md §2: a connector adapter's output is a list of
`SourceCandidate` — it never creates an event or writes an article.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SourceCandidate(BaseModel):
    source_id: UUID
    external_id: str
    url: str
    canonical_url: str
    title: str
    excerpt: str | None = None
    body: str | None = None
    author: str | None = None
    language: str
    published_at: datetime
    updated_at: datetime | None = None
    fetched_at: datetime
    raw: dict[str, Any] = Field(default_factory=dict)
