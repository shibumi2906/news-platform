"""Provider-neutral social adapters; Telegram is the first production implementation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class DistributionError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class DeliveryResult:
    external_id: str
    external_url: str | None = None
    provider_request_id: str | None = None


class DistributionAdapter(Protocol):
    kind: str

    async def publish(
        self,
        *,
        payload: dict[str, Any],
        config: dict[str, Any],
        credential_ref: str | None,
        idempotency_key: str,
    ) -> DeliveryResult: ...


def resolve_secret(credential_ref: str | None) -> str:
    if not credential_ref:
        raise DistributionError("missing_credentials", retryable=False)
    value = os.environ.get(f"DISTRIBUTION_SECRET_{credential_ref}")
    if not value:
        raise DistributionError("missing_credentials", retryable=False)
    return value


class TelegramAdapter:
    kind = "telegram"

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")

    async def publish(
        self,
        *,
        payload: dict[str, Any],
        config: dict[str, Any],
        credential_ref: str | None,
        idempotency_key: str,
    ) -> DeliveryResult:
        token = resolve_secret(credential_ref)
        chat_id = config.get("chat_id")
        if not isinstance(chat_id, str) or not chat_id:
            raise DistributionError("invalid_channel_config", retryable=False)
        title = str(payload.get("title", "News update"))
        summary = str(payload.get("summary", ""))
        text = f"{title}\n\n{summary}"[:4096]
        try:
            response = await self.client.post(
                f"{self.base_url}/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": False},
                headers={"X-Idempotency-Key": idempotency_key},
            )
        except httpx.TimeoutException:
            raise DistributionError("telegram_timeout", retryable=True) from None
        except httpx.RequestError:
            raise DistributionError("telegram_transport_error", retryable=True) from None
        if response.status_code == 429 or response.status_code >= 500:
            raise DistributionError("telegram_temporarily_unavailable", retryable=True)
        if response.status_code >= 400:
            raise DistributionError("telegram_request_rejected", retryable=False)
        try:
            data = response.json()
            message_id = str(data["result"]["message_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DistributionError("telegram_invalid_response", retryable=True) from exc
        return DeliveryResult(
            external_id=message_id,
            external_url=None,
            provider_request_id=response.headers.get("x-request-id"),
        )


class OAuthAdapter:
    """Shared, bounded HTTP boundary for OAuth-protected social APIs."""

    kind: str

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        credential_ref: str | None,
        idempotency_key: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = resolve_secret(credential_ref)
        try:
            response = await self.client.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                data=data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": idempotency_key,
                    "X-Idempotency-Key": idempotency_key,
                },
            )
        except httpx.TimeoutException:
            raise DistributionError(f"{self.kind}_timeout", retryable=True) from None
        except httpx.RequestError:
            raise DistributionError(f"{self.kind}_transport_error", retryable=True) from None
        if response.status_code == 429:
            raise DistributionError(f"{self.kind}_rate_limited", retryable=True)
        if response.status_code >= 500:
            raise DistributionError(f"{self.kind}_temporarily_unavailable", retryable=True)
        if response.status_code >= 400:
            raise DistributionError(f"{self.kind}_request_rejected", retryable=False)
        try:
            payload = response.json()
        except ValueError as exc:
            raise DistributionError(f"{self.kind}_invalid_response", retryable=True) from exc
        if not isinstance(payload, dict):
            raise DistributionError(f"{self.kind}_invalid_response", retryable=True)
        return payload


def _text(payload: dict[str, Any], limit: int) -> str:
    title = str(payload.get("title", "News update"))
    summary = str(payload.get("summary", ""))
    url = payload.get("article_url")
    return f"{title}\n\n{summary}{f'\n\n{url}' if isinstance(url, str) else ''}"[:limit]


def _media_url(payload: dict[str, Any]) -> str:
    value = payload.get("media_url")
    if not isinstance(value, str) or not value.startswith("https://"):
        raise DistributionError("media_url_unavailable", retryable=False)
    return value


class FacebookAdapter(OAuthAdapter):
    kind = "facebook"

    async def publish(
        self,
        *,
        payload: dict[str, Any],
        config: dict[str, Any],
        credential_ref: str | None,
        idempotency_key: str,
    ) -> DeliveryResult:
        page_id = config["page_id"]
        if payload["content_type"] == "image":
            data = await self._request(
                "POST",
                f"/{page_id}/photos",
                credential_ref=credential_ref,
                idempotency_key=idempotency_key,
                data={"url": _media_url(payload), "caption": _text(payload, 63_206)},
            )
        elif payload["content_type"] == "video":
            data = await self._request(
                "POST",
                f"/{page_id}/videos",
                credential_ref=credential_ref,
                idempotency_key=idempotency_key,
                data={"file_url": _media_url(payload), "description": _text(payload, 63_206)},
            )
        else:
            data = await self._request(
                "POST",
                f"/{page_id}/feed",
                credential_ref=credential_ref,
                idempotency_key=idempotency_key,
                data={"message": _text(payload, 63_206), "link": payload.get("article_url")},
            )
        external_id = data.get("id") or data.get("post_id")
        if not isinstance(external_id, str):
            raise DistributionError("facebook_invalid_response", retryable=True)
        return DeliveryResult(external_id=external_id)


class InstagramAdapter(OAuthAdapter):
    kind = "instagram"

    async def publish(
        self,
        *,
        payload: dict[str, Any],
        config: dict[str, Any],
        credential_ref: str | None,
        idempotency_key: str,
    ) -> DeliveryResult:
        account_id = config["instagram_account_id"]
        is_video = payload["content_type"] == "video"
        container = await self._request(
            "POST",
            f"/{account_id}/media",
            credential_ref=credential_ref,
            idempotency_key=idempotency_key,
            data={
                "media_type": "REELS" if is_video else "IMAGE",
                "video_url" if is_video else "image_url": _media_url(payload),
                "caption": _text(payload, 2_200),
            },
        )
        creation_id = container.get("id")
        if not isinstance(creation_id, str):
            raise DistributionError("instagram_invalid_response", retryable=True)
        published = await self._request(
            "POST",
            f"/{account_id}/media_publish",
            credential_ref=credential_ref,
            idempotency_key=idempotency_key,
            data={"creation_id": creation_id},
        )
        external_id = published.get("id")
        if not isinstance(external_id, str):
            raise DistributionError("instagram_invalid_response", retryable=True)
        return DeliveryResult(external_id=external_id)


class TikTokAdapter(OAuthAdapter):
    kind = "tiktok"

    async def publish(
        self,
        *,
        payload: dict[str, Any],
        config: dict[str, Any],
        credential_ref: str | None,
        idempotency_key: str,
    ) -> DeliveryResult:
        data = await self._request(
            "POST",
            "/v2/post/publish/video/init/",
            credential_ref=credential_ref,
            idempotency_key=idempotency_key,
            json={
                "post_info": {
                    "title": _text(payload, 2_200),
                    "privacy_level": config.get("privacy_level", "PUBLIC_TO_EVERYONE"),
                    "disable_duet": bool(config.get("disable_duet", False)),
                    "disable_comment": bool(config.get("disable_comment", False)),
                    "disable_stitch": bool(config.get("disable_stitch", False)),
                },
                "source_info": {"source": "PULL_FROM_URL", "video_url": _media_url(payload)},
            },
        )
        publish_id = (
            data.get("data", {}).get("publish_id") if isinstance(data.get("data"), dict) else None
        )
        if not isinstance(publish_id, str):
            raise DistributionError("tiktok_invalid_response", retryable=True)
        return DeliveryResult(external_id=publish_id)


class XAdapter(OAuthAdapter):
    kind = "x"

    async def publish(
        self,
        *,
        payload: dict[str, Any],
        config: dict[str, Any],
        credential_ref: str | None,
        idempotency_key: str,
    ) -> DeliveryResult:
        # X v2 accepts tweet creation directly. Media upload is deliberately
        # rejected at scheduling until an account's upload authorization is set.
        if payload["content_type"] in {"image", "video"}:
            raise DistributionError("x_media_upload_not_authorized", retryable=False)
        data = await self._request(
            "POST",
            "/2/tweets",
            credential_ref=credential_ref,
            idempotency_key=idempotency_key,
            json={"text": _text(payload, 280)},
        )
        nested = data.get("data")
        external_id = nested.get("id") if isinstance(nested, dict) else None
        if not isinstance(external_id, str):
            raise DistributionError("x_invalid_response", retryable=True)
        return DeliveryResult(
            external_id=external_id, external_url=f"https://x.com/i/web/status/{external_id}"
        )


class YouTubeAdapter(OAuthAdapter):
    kind = "youtube"

    async def publish(
        self,
        *,
        payload: dict[str, Any],
        config: dict[str, Any],
        credential_ref: str | None,
        idempotency_key: str,
    ) -> DeliveryResult:
        token = resolve_secret(credential_ref)
        media_url = _media_url(payload)
        try:
            media = await self.client.get(media_url)
            media.raise_for_status()
            initialization = await self.client.post(
                f"{self.base_url}/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                json={
                    "snippet": {
                        "title": str(payload.get("title", "News update"))[:100],
                        "description": _text(payload, 5_000),
                        "channelId": config["channel_id"],
                    },
                    "status": {
                        "privacyStatus": config.get("privacy_status", "private"),
                        "selfDeclaredMadeForKids": bool(config.get("made_for_kids", False)),
                    },
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Upload-Content-Type": str(payload.get("media_mime_type", "video/mp4")),
                    "X-Upload-Content-Length": str(len(media.content)),
                    "X-Idempotency-Key": idempotency_key,
                },
            )
            if initialization.status_code == 429 or initialization.status_code >= 500:
                raise DistributionError("youtube_temporarily_unavailable", retryable=True)
            if initialization.status_code >= 400:
                raise DistributionError("youtube_request_rejected", retryable=False)
            upload_url = initialization.headers.get("Location")
            if not upload_url:
                raise DistributionError("youtube_invalid_response", retryable=True)
            uploaded = await self.client.put(
                upload_url,
                content=media.content,
                headers={
                    "Content-Type": str(payload.get("media_mime_type", "video/mp4")),
                    "Authorization": f"Bearer {token}",
                },
            )
            if uploaded.status_code == 429 or uploaded.status_code >= 500:
                raise DistributionError("youtube_temporarily_unavailable", retryable=True)
            if uploaded.status_code >= 400:
                raise DistributionError("youtube_request_rejected", retryable=False)
            data = uploaded.json()
        except DistributionError:
            raise
        except httpx.TimeoutException:
            raise DistributionError("youtube_timeout", retryable=True) from None
        except httpx.RequestError:
            raise DistributionError("youtube_transport_error", retryable=True) from None
        except ValueError:
            raise DistributionError("youtube_invalid_response", retryable=True) from None
        external_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(external_id, str):
            raise DistributionError("youtube_invalid_response", retryable=True)
        return DeliveryResult(
            external_id=external_id, external_url=f"https://youtu.be/{external_id}"
        )
