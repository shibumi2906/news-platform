"""UTC time helpers.

All timestamps are stored and exchanged in UTC, ISO 8601
(docs/00_GLOSSARY_AND_CONVENTIONS.md §4).
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso8601(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
