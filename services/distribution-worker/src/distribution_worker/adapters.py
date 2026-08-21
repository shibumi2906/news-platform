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
