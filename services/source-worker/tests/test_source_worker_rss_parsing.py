from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from source_worker.rss import canonicalize_url, parse_rss_feed

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"


def test_canonicalize_url_strips_query_and_fragment() -> None:
    assert (
        canonicalize_url("https://news.example.com/a?utm_source=feed#top")
        == "https://news.example.com/a"
    )


def test_parse_rss_feed_skips_entries_without_a_link() -> None:
    source_id = uuid4()
    fetched_at = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

    candidates = parse_rss_feed(FIXTURE.read_bytes(), source_id=source_id, fetched_at=fetched_at)

    assert len(candidates) == 2
    assert all(candidate.url for candidate in candidates)


def test_parse_rss_feed_uses_guid_as_external_id_when_present() -> None:
    source_id = uuid4()
    fetched_at = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

    candidates = parse_rss_feed(FIXTURE.read_bytes(), source_id=source_id, fetched_at=fetched_at)

    first = candidates[0]
    assert first.external_id == "urn:example:first-headline"
    assert first.title == "First headline"
    assert first.canonical_url == "https://news.example.com/articles/first-headline"
    assert first.author == "jane@example.com (Jane Reporter)"
    assert first.body is not None and "Full body" in first.body
    assert first.published_at.tzinfo is not None


def test_parse_rss_feed_falls_back_to_link_as_external_id() -> None:
    source_id = uuid4()
    fetched_at = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

    candidates = parse_rss_feed(FIXTURE.read_bytes(), source_id=source_id, fetched_at=fetched_at)

    second = candidates[1]
    assert second.external_id == second.url == "https://news.example.com/articles/second-headline"


def test_parse_rss_feed_raw_payload_is_json_serializable() -> None:
    import json

    source_id = uuid4()
    fetched_at = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

    candidates = parse_rss_feed(FIXTURE.read_bytes(), source_id=source_id, fetched_at=fetched_at)

    for candidate in candidates:
        json.dumps(candidate.raw)  # raises TypeError if not serializable
