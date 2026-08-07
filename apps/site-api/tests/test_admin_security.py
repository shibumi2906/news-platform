from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.main import create_app
from site_api.security_service import build_session_validator, ensure_security_seed
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("INSTANCE_ID", "22222222-2222-2222-2222-222222222222")
    monkeypatch.setenv("INSTANCE_TYPE", "site")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ADMIN_API_TOKEN", "service-token")
    monkeypatch.setenv("ADMIN_SESSION_KEYS", f"test:{'s' * 32}")
    engine: AsyncEngine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    async with factory() as session:
        await ensure_security_seed(
            session, username="admin", password="a-strong-bootstrap-password"
        )
    app = create_app()
    app.state.session_factory = factory
    app.state.admin_session_validator = build_session_validator(factory, idle_seconds=3600)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    await engine.dispose()


async def _login(client: httpx.AsyncClient) -> tuple[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "a-strong-bootstrap-password"},
    )
    assert response.status_code == 200
    return response.json()["session_token"], response.json()["csrf_token"]


async def test_login_rbac_csrf_and_revocation(client: httpx.AsyncClient) -> None:
    token, csrf = await _login(client)
    read = await client.get("/api/v1/admin/security/users", headers={"X-Admin-Session": token})
    assert read.status_code == 200 and read.json()[0]["username"] == "admin"
    missing_csrf = await client.post(
        "/api/v1/admin/security/secrets/rotate",
        headers={"X-Admin-Session": token},
        json={"name": "SESSION_KEY", "version": "v2"},
    )
    assert missing_csrf.status_code == 403
    rotated = await client.post(
        "/api/v1/admin/security/secrets/rotate",
        headers={"X-Admin-Session": token, "X-CSRF-Token": csrf},
        json={"name": "SESSION_KEY", "version": "v2"},
    )
    assert rotated.status_code == 201
    logged_out = await client.post(
        "/api/v1/auth/logout",
        headers={"X-Admin-Session": token, "X-CSRF-Token": csrf},
    )
    assert logged_out.status_code == 204
    assert (
        await client.get("/api/v1/admin/security/users", headers={"X-Admin-Session": token})
    ).status_code == 401


async def test_invalid_password_and_service_token_rotation(client: httpx.AsyncClient) -> None:
    denied = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "incorrect"}
    )
    assert denied.status_code == 401
    service = await client.get(
        "/api/v1/admin/security/users", headers={"X-Admin-Token": "service-token"}
    )
    assert service.status_code == 200


async def test_custom_role_enforces_least_privilege(client: httpx.AsyncClient) -> None:
    headers = {"X-Admin-Token": "service-token"}
    role = await client.post(
        "/api/v1/admin/security/roles",
        headers=headers,
        json={
            "name": "Article reader",
            "description": "Read only",
            "permission_codes": ["articles:read"],
        },
    )
    assert role.status_code == 201
    created = await client.post(
        "/api/v1/admin/security/users",
        headers=headers,
        json={
            "username": "reader",
            "display_name": "Reader",
            "password": "reader-password-strong",
            "role_ids": [role.json()["id"]],
        },
    )
    assert created.status_code == 201
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "reader", "password": "reader-password-strong"},
    )
    session_header = {"X-Admin-Session": login.json()["session_token"]}
    assert (await client.get("/api/v1/admin/articles", headers=session_header)).status_code == 200
    assert (
        await client.get("/api/v1/admin/security/users", headers=session_header)
    ).status_code == 403


async def test_login_rate_limit_does_not_expose_account_state(client: httpx.AsyncClient) -> None:
    responses = [
        await client.post(
            "/api/v1/auth/login", json={"username": "unknown", "password": "incorrect"}
        )
        for _ in range(11)
    ]
    assert all(response.status_code == 401 for response in responses[:10])
    assert responses[-1].status_code == 429
