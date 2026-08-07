"""Small service-token foundation for admin APIs.

Browser sessions terminate at the Next.js BFF.  The BFF authenticates to the
Python admin APIs with this optional token, keeping credentials out of browser
JavaScript.  Installations should set ``ADMIN_API_TOKEN``; leaving it unset is
supported only for local development and existing test fixtures.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request


async def require_admin_api_token(
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    configured = request.app.state.settings.admin_api_token
    if configured is None:
        return
    supplied = x_admin_token or ""
    if not secrets.compare_digest(supplied, configured.get_secret_value()):
        raise HTTPException(status_code=401, detail="admin authentication required")
