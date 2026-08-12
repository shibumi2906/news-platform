from __future__ import annotations

# ruff: noqa: E501
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from source_worker.api import collect_api_source


def _config(**overrides: object) -> dict[str, object]:
    return {
        "items_path": "data.articles",
        "mapping": {
            "id": "id",
            "title": "title",
            "url": "url",
            "published_at": "published",
            "author": "author",
            "content": "body",
            "summary": "summary",
            "language": "language",
        },
        **overrides,
    }


async def test_api_connector_extracts_json_optional_fields_and_relative_url() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "articles": [
                        {
                            "id": "one",
                            "title": "Headline",
                            "url": "/news/one",
                            "published": "2026-08-10T12:00:00Z",
                            "author": "Reporter",
                            "body": "Full text",
                            "language": "en",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, error = await collect_api_source(
            client,
            source_id=uuid4(),
            base_url="https://api.example.test/v1/articles",
            config=_config(),
            fetched_at=datetime(2026, 8, 11, tzinfo=UTC),
            user_agent="api-agent",
            timeout_seconds=1,
        )
    assert error is None
    assert candidates[0].url == "https://api.example.test/news/one"
    assert candidates[0].author == "Reporter"
    assert candidates[0].excerpt is None
    assert candidates[0].published_at == datetime(2026, 8, 10, 12, tzinfo=UTC)


async def test_api_connector_pagination_and_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_API_TOKEN", "token-value")
    pages: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token-value"
        pages.append(str(request.url.params.get("page")))
        page = request.url.params.get("page")
        return httpx.Response(
            200,
            json={
                "data": {
                    "articles": (
                        [{"id": page, "title": page, "url": f"/{page}"}] if page != "3" else []
                    )
                }
            },
        )

    config = _config(
        auth_env="TEST_API_TOKEN", pagination={"page_param": "page", "start": 1, "max_pages": 3}
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, error = await collect_api_source(
            client,
            source_id=uuid4(),
            base_url="https://api.example.test/items",
            config=config,
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None
    assert pages == ["1", "2", "3"]
    assert [candidate.external_id for candidate in candidates] == ["1", "2"]


async def test_api_connector_skips_malformed_items_and_reports_bad_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"articles": [{"id": "bad"}, {"id": "ok", "title": "Ok", "url": "/ok"}]}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, error = await collect_api_source(
            client,
            source_id=uuid4(),
            base_url="https://api.example.test",
            config=_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None and [candidate.external_id for candidate in candidates] == ["ok"]

    async def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed)) as client:
        _, error = await collect_api_source(
            client,
            source_id=uuid4(),
            base_url="https://api.example.test",
            config=_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error == "invalid_json"


async def test_api_connector_retries_network_error_and_supports_different_mapping() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(
            200, json={"results": [{"uuid": "two", "name": "Other", "link": "/two"}]}
        )

    config = {"items_path": "results", "mapping": {"id": "uuid", "title": "name", "url": "link"}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, error = await collect_api_source(
            client,
            source_id=uuid4(),
            base_url="https://api.example.test",
            config=config,
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=0.01,
        )
    assert error is None and attempts == 2
    assert candidates[0].external_id == "two"


async def test_api_connector_missing_secret_fails_closed() -> None:
    os.environ.pop("MISSING_API_TOKEN", None)
    async with httpx.AsyncClient() as client:
        candidates, error = await collect_api_source(
            client,
            source_id=uuid4(),
            base_url="https://api.example.test",
            config=_config(auth_env="MISSING_API_TOKEN"),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert candidates == [] and error == "missing_api_secret"
