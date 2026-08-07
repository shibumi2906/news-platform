"""Fail-closed validation of Site-owned administrator sessions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
from common.logging import get_correlation_id, get_logger
from common.security import Principal

logger = get_logger(__name__)
SessionValidator = Callable[[Principal, str, str | None, bool], Awaitable[bool]]


def build_remote_session_validator(
    client: httpx.AsyncClient, *, service_token: str
) -> SessionValidator:
    async def validate(
        principal: Principal, token: str, csrf_token: str | None, unsafe: bool
    ) -> bool:
        if not service_token:
            return False
        headers = {"X-Admin-Token": service_token}
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Request-Id"] = correlation_id
        try:
            response = await client.post(
                "/api/v1/auth/introspect",
                headers=headers,
                json={
                    "session_token": token,
                    "csrf_token": csrf_token,
                    "unsafe": unsafe,
                },
            )
            if response.status_code != 200:
                return False
            payload = response.json()
            return isinstance(payload, dict) and payload.get("active") is True
        except (httpx.RequestError, ValueError):
            logger.warning("admin_session_introspection_failed")
            return False

    return validate
