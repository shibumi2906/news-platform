from __future__ import annotations

import httpx
import pytest
from distribution_worker.adapters import (
    DistributionError,
    FacebookAdapter,
    InstagramAdapter,
    TelegramAdapter,
    TikTokAdapter,
    XAdapter,
    YouTubeAdapter,
)


async def test_telegram_adapter_success_and_redacted_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISTRIBUTION_SECRET_TEST_BOT", "top-secret-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "top-secret-token" in str(request.url)
        assert request.headers["x-idempotency-key"] == "job-key"
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await TelegramAdapter(client, base_url="https://telegram.test").publish(
            payload={"title": "Headline", "summary": "Summary"},
            config={"chat_id": "@channel"},
            credential_ref="TEST_BOT",
            idempotency_key="job-key",
        )
    assert result.external_id == "42"


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (401, False)])
async def test_telegram_adapter_error_states(
    monkeypatch: pytest.MonkeyPatch, status: int, retryable: bool
) -> None:
    monkeypatch.setenv("DISTRIBUTION_SECRET_TEST_BOT", "secret")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, text="sensitive"))
    ) as client:
        with pytest.raises(DistributionError) as raised:
            await TelegramAdapter(client, base_url="https://telegram.test").publish(
                payload={"title": "PII must not enter the exception"},
                config={"chat_id": "1"},
                credential_ref="TEST_BOT",
                idempotency_key="safe-key",
            )
    assert raised.value.retryable is retryable
    assert "sensitive" not in str(raised.value)
    assert "secret" not in str(raised.value)


async def test_telegram_transport_error_never_exposes_bot_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISTRIBUTION_SECRET_TEST_BOT", "top-secret-token")

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("top-secret-token", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DistributionError) as raised:
            await TelegramAdapter(client, base_url="https://telegram.test").publish(
                payload={"title": "Headline"},
                config={"chat_id": "1"},
                credential_ref="TEST_BOT",
                idempotency_key="safe-key",
            )
    assert raised.value.code == "telegram_transport_error"
    assert raised.value.retryable
    assert "top-secret-token" not in str(raised.value)


@pytest.mark.parametrize(
    ("adapter_type", "base_url", "config", "payload", "response", "expected_id"),
    [
        (
            FacebookAdapter,
            "https://facebook.test",
            {"page_id": "page"},
            {"content_type": "text"},
            {"id": "post-1"},
            "post-1",
        ),
        (
            InstagramAdapter,
            "https://facebook.test",
            {"instagram_account_id": "ig"},
            {"content_type": "image", "media_url": "https://cdn.test/image.jpg"},
            {"id": "post-2"},
            "post-2",
        ),
        (
            TikTokAdapter,
            "https://tiktok.test",
            {},
            {"content_type": "video", "media_url": "https://cdn.test/video.mp4"},
            {"data": {"publish_id": "publish-1"}},
            "publish-1",
        ),
        (
            XAdapter,
            "https://x.test",
            {},
            {"content_type": "text"},
            {"data": {"id": "tweet-1"}},
            "tweet-1",
        ),
    ],
)
async def test_social_adapters_publish_with_idempotency(
    monkeypatch: pytest.MonkeyPatch,
    adapter_type: type[FacebookAdapter | InstagramAdapter | TikTokAdapter | XAdapter],
    base_url: str,
    config: dict[str, str],
    payload: dict[str, str],
    response: dict[str, object],
    expected_id: str,
) -> None:
    monkeypatch.setenv("DISTRIBUTION_SECRET_SOCIAL", "secret")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        # Instagram requires creation then publication; both response shapes use id.
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await adapter_type(client, base_url=base_url).publish(
            payload={"title": "Headline", "summary": "Summary", **payload},
            config=config,
            credential_ref="SOCIAL",
            idempotency_key="stable-key",
        )
    assert result.external_id == expected_id
    assert all(call.headers["x-idempotency-key"] == "stable-key" for call in calls)


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (400, False)])
async def test_social_error_mapping_and_missing_credentials(
    monkeypatch: pytest.MonkeyPatch, status: int, retryable: bool
) -> None:
    monkeypatch.setenv("DISTRIBUTION_SECRET_SOCIAL", "secret")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    ) as client:
        with pytest.raises(DistributionError) as raised:
            await XAdapter(client, base_url="https://x.test").publish(
                payload={"title": "Headline", "content_type": "text"},
                config={},
                credential_ref="SOCIAL",
                idempotency_key="safe-key",
            )
    assert raised.value.retryable is retryable
    monkeypatch.delenv("DISTRIBUTION_SECRET_SOCIAL")
    async with httpx.AsyncClient() as client:
        with pytest.raises(DistributionError, match="missing_credentials"):
            await XAdapter(client, base_url="https://x.test").publish(
                payload={"title": "Headline", "content_type": "text"},
                config={},
                credential_ref="SOCIAL",
                idempotency_key="safe-key",
            )


async def test_youtube_resumable_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTION_SECRET_YOUTUBE", "secret")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/video.mp4":
            return httpx.Response(200, content=b"video")
        if "upload/youtube" in request.url.path:
            return httpx.Response(200, headers={"Location": "https://youtube.test/resumable"})
        return httpx.Response(200, json={"id": "yt-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as local_client:
        result = await YouTubeAdapter(local_client, base_url="https://youtube.test").publish(
            payload={
                "title": "Headline",
                "content_type": "video",
                "media_url": "https://cdn.test/video.mp4",
                "media_mime_type": "video/mp4",
            },
            config={"channel_id": "channel"},
            credential_ref="YOUTUBE",
            idempotency_key="stable-key",
        )
    assert result.external_id == "yt-1"
