from __future__ import annotations

import uuid

import httpx
from common.security import Principal
from integrator_api.security import build_remote_session_validator


def _principal() -> Principal:
    return Principal(
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        actor="editor",
        permissions=frozenset({"sources:manage"}),
        expires_at=2_000_000_000,
        mfa_verified=True,
        auth_method="password",
    )


async def test_remote_session_validator_forwards_csrf_without_exposing_it() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["X-Admin-Token"]
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"active": True})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://site-api"
    ) as client:
        validator = build_remote_session_validator(client, service_token="service-secret")
        assert await validator(_principal(), "signed-session", "csrf-secret", True)
    assert seen["authorization"] == "service-secret"
    assert '"unsafe":true' in str(seen["body"])
    assert '"csrf_token":"csrf-secret"' in str(seen["body"])


async def test_remote_session_validator_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://site-api"
    ) as client:
        validator = build_remote_session_validator(client, service_token="service-secret")
        assert not await validator(_principal(), "signed-session", None, False)
        assert not await build_remote_session_validator(client, service_token="")(
            _principal(), "signed-session", None, False
        )
