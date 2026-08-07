from __future__ import annotations

import pytest
from processing_worker.ai_gateway import (
    AIGateway,
    AIGatewayError,
    AIProviderError,
    AIRequest,
    FakeAIProvider,
    build_gateway,
)


async def _no_sleep(_: float) -> None:
    return None


async def test_gateway_retries_then_returns_structured_usage() -> None:
    provider = FakeAIProvider(
        {"draft": {"title": "T", "lead": "L", "body": "B", "summary": "S"}},
        failures={"draft": 1},
    )
    result = await AIGateway([provider], sleep=_no_sleep).complete(
        AIRequest("draft", "system", "user", {})
    )
    assert result.provider == "fake"
    assert result.attempts == 2
    assert result.prompt_tokens > 0


async def test_gateway_falls_back_to_second_provider() -> None:
    failing = FakeAIProvider(failures={"draft": 10})
    succeeding = FakeAIProvider({"draft": {"ok": True}})
    result = await AIGateway(
        [failing, succeeding], max_attempts_per_provider=1, sleep=_no_sleep
    ).complete(AIRequest("draft", "", "", {}))
    assert result.output == {"ok": True}
    assert result.attempts == 2


async def test_fake_provider_rejects_unknown_operation_without_retry() -> None:
    with pytest.raises(AIGatewayError, match="unsupported_operation"):
        await AIGateway([FakeAIProvider()], sleep=_no_sleep).complete(
            AIRequest("unknown", "", "", {})
        )


def test_provider_error_does_not_expose_payload() -> None:
    error = AIProviderError("provider_timeout")
    assert str(error) == "provider_timeout"


def test_provider_registry_rejects_uninstalled_adapter() -> None:
    with pytest.raises(ValueError, match="not installed"):
        build_gateway("paid-provider", max_attempts_per_provider=1)
