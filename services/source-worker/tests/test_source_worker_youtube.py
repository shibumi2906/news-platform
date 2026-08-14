from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from source_worker.youtube import collect_youtube_source


def _config(**overrides: object) -> dict[str, object]:
    return {"api_key_env": "YOUTUBE_TEST_KEY", "channel_id": "UC123", **overrides}


def _video(video_id: str, **snippet: object) -> dict[str, object]:
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": f"Video {video_id}",
            "publishedAt": "2026-08-12T10:00:00Z",
            "channelTitle": "Channel",
            "description": "Description",
            "thumbnails": {"medium": {"url": "https://img.test/thumbnail.jpg"}},
            **snippet,
        },
    }


async def test_youtube_channel_and_playlist_ingestion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_TEST_KEY", "secret")
    requests: list[httpx.URL] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url)
        if request.url.path.endswith("playlistItems"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "contentDetails": {"videoId": "playlist-video"},
                            "snippet": {"title": "Playlist video", "channelTitle": "Playlist"},
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"items": [_video("channel-video", defaultLanguage="es")]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        channel, error = await collect_youtube_source(
            client,
            source_id=uuid4(),
            config=_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
        playlist, playlist_error = await collect_youtube_source(
            client,
            source_id=uuid4(),
            config=_config(playlist_id="PL123"),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None and playlist_error is None
    assert channel[0].url == "https://www.youtube.com/watch?v=channel-video"
    assert channel[0].language == "es"
    assert channel[0].raw["thumbnails"] == {"medium": {"url": "https://img.test/thumbnail.jpg"}}
    assert playlist[0].external_id == "playlist-video"
    assert requests[0].params["channelId"] == "UC123"
    assert requests[1].params["playlistId"] == "PL123"


async def test_youtube_channel_url_and_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_TEST_KEY", "secret")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("channels"):
            assert request.url.params["forHandle"] == "publisher"
            return httpx.Response(200, json={"items": [{"id": "UCresolved"}]})
        token = request.url.params.get("pageToken")
        return httpx.Response(
            200,
            json={
                "items": [_video("one" if token is None else "two")],
                **({"nextPageToken": "next"} if token is None else {}),
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, error = await collect_youtube_source(
            client,
            source_id=uuid4(),
            config=_config(
                channel_id="", channel_url="https://youtube.test/@publisher", max_pages=2
            ),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None
    assert [candidate.external_id for candidate in candidates] == ["one", "two"]


async def test_youtube_tolerates_optional_and_malformed_items_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YOUTUBE_TEST_KEY", "secret")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    "bad",
                    {"id": {}},
                    _video("same", title=""),
                    _video("same"),
                    _video("same"),
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidates, error = await collect_youtube_source(
            client,
            source_id=uuid4(),
            config=_config(language="fr"),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error is None
    assert len(candidates) == 1
    assert candidates[0].language == "fr"
    assert candidates[0].author == "Channel"


async def test_youtube_reports_malformed_response_and_retries_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YOUTUBE_TEST_KEY", "secret")
    attempts = 0

    async def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json={"items": [_video("retried")]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(retry_handler)) as client:
        candidates, error = await collect_youtube_source(
            client,
            source_id=uuid4(),
            config=_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=0.01,
        )
    assert error is None and attempts == 2 and candidates[0].external_id == "retried"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    ) as client:
        _, error = await collect_youtube_source(
            client,
            source_id=uuid4(),
            config=_config(),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert error == "invalid_youtube_response"


async def test_youtube_fails_closed_without_api_key() -> None:
    async with httpx.AsyncClient() as client:
        candidates, error = await collect_youtube_source(
            client,
            source_id=uuid4(),
            config=_config(api_key_env="MISSING_YOUTUBE_KEY"),
            fetched_at=datetime.now(UTC),
            user_agent="agent",
            timeout_seconds=1,
        )
    assert candidates == [] and error == "missing_youtube_api_key"
