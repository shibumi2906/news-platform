from __future__ import annotations

import httpx
import pytest
from distribution_worker.adapters import DistributionError, TelegramAdapter


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
