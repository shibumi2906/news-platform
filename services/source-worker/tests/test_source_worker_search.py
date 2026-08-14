from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from source_worker.search import collect_gemini_search_source, collect_google_search_source


def _google_config(**overrides: object) -> dict[str, object]:
    return {
        "api_key_env": "GOOGLE_SEARCH_TEST_KEY",
        "search_engine_id": "engine-id",
        "query": "configured query",
        **overrides,
    }


def _gemini_config(**overrides: object) -> dict[str, object]:
    return {"api_key_env": "GEMINI_TEST_KEY", "query": "configured query", **overrides}


def _result(url: str, title: str = "Result", **extra: object) -> dict[str, object]:
    return {"link": url, "title": title, "snippet": "Summary", **extra}


async def test_google_search_extracts_configured_result_and_optional_publication_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_SEARCH_TEST_KEY", "secret")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "configured query"
        assert request.url.params["hl"] == "en-US"
        assert request.url.params["gl"] == "US"
        return httpx.Response(
            200,
            json={
                "items": [
                    _result(
                        "https://news.test/item?utm_source=x",
                        pagemap={"metatags": [{"article:published_time": "2026-08-10T12:00:00Z"}]},
                    )
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, error = await collect_google_search_source(
            client,
            source_id=uuid4(),
            config=_google_config(locale="en-US", language="en", region="US"),
            fetched_at=datetime(2026, 8, 11, tzinfo=UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None
    assert candidates[0].canonical_url == "https://news.test/item"
    assert candidates[0].published_at == datetime(2026, 8, 10, 12, tzinfo=UTC)
    assert candidates[0].excerpt == "Summary"


async def test_google_search_paginates_respects_limit_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_SEARCH_TEST_KEY", "secret")
    starts: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        start = str(request.url.params["start"])
        starts.append(start)
        return httpx.Response(
            200,
            json={
                "items": [
                    _result("https://news.test/one"),
                    _result("https://news.test/one?utm=x"),
                    _result(f"https://news.test/{start}"),
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, error = await collect_google_search_source(
            client,
            source_id=uuid4(),
            config=_google_config(page_size=2, max_pages=3, limit=3),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None
    assert starts == ["1", "3"]
    assert [item.canonical_url for item in candidates] == [
        "https://news.test/one",
        "https://news.test/1",
        "https://news.test/3",
    ]


async def test_google_search_handles_malformed_response_retry_and_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_SEARCH_TEST_KEY", "secret")
    attempts = 0

    async def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json={"items": ["invalid", _result("https://news.test/ok")]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(retry_handler)) as client:
        candidates, error = await collect_google_search_source(
            client,
            source_id=uuid4(),
            config=_google_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=0.01,
        )
    assert error is None and attempts == 2 and len(candidates) == 1
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"items": {}}))
    ) as client:
        _, error = await collect_google_search_source(
            client,
            source_id=uuid4(),
            config=_google_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error == "invalid_google_search_response"
    monkeypatch.delenv("MISSING_GOOGLE_KEY", raising=False)
    async with httpx.AsyncClient() as client:
        candidates, error = await collect_google_search_source(
            client,
            source_id=uuid4(),
            config=_google_config(api_key_env="MISSING_GOOGLE_KEY"),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert candidates == [] and error == "missing_google_search_api_key"


async def test_gemini_search_extracts_grounded_web_results_and_respects_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_TEST_KEY", "secret")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret"
        payload = __import__("json").loads(request.content)
        assert payload["tools"] == [{"google_search": {}}]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Gemini summary"}]},
                        "groundingMetadata": {
                            "groundingChunks": [
                                {"web": {"uri": "https://news.test/a", "title": "A"}},
                                {"web": {"uri": "https://news.test/a?utm=x", "title": "Duplicate"}},
                                {"web": {"uri": "https://news.test/b", "title": "B"}},
                            ]
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, error = await collect_gemini_search_source(
            client,
            source_id=uuid4(),
            config=_gemini_config(limit=2, locale="en-US", region="US"),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None
    assert [candidate.title for candidate in candidates] == ["A", "B"]
    assert candidates[0].body == "Gemini summary"


async def test_gemini_search_handles_malformed_response_retry_and_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_TEST_KEY", "secret")
    attempts = 0

    async def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(
            200, json={"candidates": [{"groundingMetadata": {"groundingChunks": ["invalid"]}}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(retry_handler)) as client:
        candidates, error = await collect_gemini_search_source(
            client,
            source_id=uuid4(),
            config=_gemini_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None and attempts == 2 and candidates == []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"candidates": {}}))
    ) as client:
        _, error = await collect_gemini_search_source(
            client,
            source_id=uuid4(),
            config=_gemini_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error == "invalid_gemini_search_response"
    monkeypatch.delenv("MISSING_GEMINI_KEY", raising=False)
    async with httpx.AsyncClient() as client:
        candidates, error = await collect_gemini_search_source(
            client,
            source_id=uuid4(),
            config=_gemini_config(api_key_env="MISSING_GEMINI_KEY"),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert candidates == [] and error == "missing_gemini_api_key"
