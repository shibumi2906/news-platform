"""Rotatable service authentication and permission-aware admin principals."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Header, HTTPException, Request

from common.security import Principal, PrincipalSigner

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class AuthContext:
    actor: str
    user_id: str | None
    session_id: str | None
    permissions: frozenset[str]
    auth_method: str
    mfa_verified: bool


async def authenticate_admin(
    request: Request,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    x_admin_session: Annotated[str | None, Header(alias="X-Admin-Session")] = None,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    configured = request.app.state.settings.admin_api_token
    if x_admin_token and configured is not None:
        accepted = configured.get_secret_value().split(",")
        if any(secrets.compare_digest(x_admin_token, token) for token in accepted if token):
            context = AuthContext(
                actor="service-admin",
                user_id=None,
                session_id=None,
                permissions=frozenset({"*"}),
                auth_method="service_token",
                mfa_verified=True,
            )
            request.state.auth_context = context
            return context
    if x_admin_session:
        try:
            signer = PrincipalSigner.from_config(
                request.app.state.settings.admin_session_keys.get_secret_value()
            )
        except ValueError as exc:
            raise HTTPException(503, "admin session verification is unavailable") from exc
        principal = signer.verify(x_admin_session)
        if principal is not None:
            if request.method not in SAFE_METHODS and not x_csrf_token:
                raise HTTPException(403, "CSRF token required")
            validator = getattr(request.app.state, "admin_session_validator", None)
            if validator is not None:
                valid = await validator(
                    principal, x_admin_session, x_csrf_token, request.method not in SAFE_METHODS
                )
                if not valid:
                    raise HTTPException(401, "admin session is inactive")
            context = _context(principal)
            request.state.auth_context = context
            return context
    raise HTTPException(status_code=401, detail="admin authentication required")


async def require_admin_api_token(
    request: Request,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    x_admin_session: Annotated[str | None, Header(alias="X-Admin-Session")] = None,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    """Backward-compatible dependency; new routes should use `require_permission`."""
    await authenticate_admin(
        request,
        x_admin_token=x_admin_token,
        x_admin_session=x_admin_session,
        x_csrf_token=x_csrf_token,
    )


def require_permission(permission: str) -> Any:
    async def dependency(
        request: Request,
        x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
        x_admin_session: Annotated[str | None, Header(alias="X-Admin-Session")] = None,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AuthContext:
        context = await authenticate_admin(
            request,
            x_admin_token=x_admin_token,
            x_admin_session=x_admin_session,
            x_csrf_token=x_csrf_token,
        )
        if "*" not in context.permissions and permission not in context.permissions:
            raise HTTPException(403, "permission denied")
        return context

    return dependency


def _context(principal: Principal) -> AuthContext:
    return AuthContext(
        actor=principal.actor,
        user_id=str(principal.user_id),
        session_id=str(principal.session_id),
        permissions=principal.permissions,
        auth_method=principal.auth_method,
        mfa_verified=principal.mfa_verified,
    )
