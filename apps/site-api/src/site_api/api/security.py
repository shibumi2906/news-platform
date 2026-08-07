"""Admin identity, sessions, RBAC, audit, and rotation metadata API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from common.auth import AuthContext, authenticate_admin, require_permission
from common.logging import get_correlation_id
from common.security import PrincipalSigner, hash_password, token_hash
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from site_domain.models import (
    AdminSession,
    AdminUser,
    AuditLog,
    Permission,
    Role,
    SecretRevision,
    role_permission,
    user_role,
)
from sqlalchemy import delete, insert, select

from site_api.security_service import login

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
admin_router = APIRouter(prefix="/api/v1/admin/security", tags=["security"])
Authenticated = Annotated[AuthContext, Depends(authenticate_admin)]
UsersRead = Annotated[AuthContext, Depends(require_permission("users:read"))]
UsersWrite = Annotated[AuthContext, Depends(require_permission("users:write"))]
AuditRead = Annotated[AuthContext, Depends(require_permission("audit:read"))]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class UserRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9._-]{2,128}$")
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=1024)
    role_ids: list[uuid.UUID] = Field(min_length=1)
    mfa_required: bool = False


class SecretRotationRequest(BaseModel):
    name: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    version: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    retire_previous_at: datetime | None = None


class RoleRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    permission_codes: list[str] = Field(min_length=1)


class RoleAssignmentRequest(BaseModel):
    role_ids: list[uuid.UUID] = Field(min_length=1)


@router.post("/login", response_model=dict[str, Any])
async def create_session(payload: LoginRequest, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    peer = request.client.host if request.client else "unknown"
    limiter_key = token_hash(f"{peer}:{payload.username.lower()}")
    if not request.app.state.login_limiter.allow(limiter_key):
        raise HTTPException(429, "too many login attempts")
    signer = PrincipalSigner.from_config(settings.admin_session_keys.get_secret_value())
    async with request.app.state.session_factory() as session:
        try:
            token, csrf_token, user, permissions = await login(
                session,
                username=payload.username,
                password=payload.password,
                signer=signer,
                ttl_seconds=settings.admin_session_ttl_seconds,
                idle_seconds=settings.admin_session_idle_seconds,
            )
        except PermissionError as exc:
            session.add(
                AuditLog(
                    actor_label="anonymous",
                    action="auth.login",
                    resource_type="session",
                    outcome="rejected",
                    correlation_id=get_correlation_id(),
                    details={"status_code": 401},
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()
            raise HTTPException(401, str(exc)) from exc
        session.add(
            AuditLog(
                actor_user_id=user.id,
                actor_label=user.username,
                action="auth.login",
                resource_type="session",
                outcome="success",
                correlation_id=get_correlation_id(),
                details={"auth_method": "password"},
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return {
            "session_token": token,
            "csrf_token": csrf_token,
            "actor": user.username,
            "permissions": sorted(permissions),
            "expires_in": settings.admin_session_ttl_seconds,
        }


@router.get("/session", response_model=dict[str, Any])
async def current_session(context: Authenticated) -> dict[str, Any]:
    return {
        "actor": context.actor,
        "permissions": sorted(context.permissions),
        "auth_method": context.auth_method,
        "mfa_verified": context.mfa_verified,
    }


@router.post("/logout", status_code=204)
async def revoke_session(request: Request, context: Authenticated) -> None:
    if context.session_id is None:
        return
    async with request.app.state.session_factory() as session:
        row = await session.get(AdminSession, uuid.UUID(context.session_id))
        if row is not None:
            row.revoked_at = datetime.now(UTC)
            await session.commit()


@admin_router.get("/users", response_model=list[dict[str, Any]])
async def list_users(request: Request, _: UsersRead) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        users = (await session.execute(select(AdminUser).order_by(AdminUser.username))).scalars()
        result = []
        for user in users:
            role_names = list(
                (
                    await session.execute(
                        select(Role.name)
                        .join(user_role, user_role.c.role_id == Role.id)
                        .where(user_role.c.user_id == user.id)
                    )
                ).scalars()
            )
            result.append(
                {
                    "id": str(user.id),
                    "username": user.username,
                    "display_name": user.display_name,
                    "is_active": user.is_active,
                    "mfa_required": user.mfa_required,
                    "roles": role_names,
                }
            )
        return result


@admin_router.post("/users", response_model=dict[str, Any], status_code=201)
async def create_user(
    payload: UserRequest,
    request: Request,
    _: UsersWrite,
) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        if (
            await session.execute(select(AdminUser).where(AdminUser.username == payload.username))
        ).scalar_one_or_none():
            raise HTTPException(409, "user already exists")
        roles = list(
            (await session.execute(select(Role).where(Role.id.in_(payload.role_ids)))).scalars()
        )
        if len(roles) != len(set(payload.role_ids)):
            raise HTTPException(422, "one or more roles do not exist")
        user = AdminUser(
            username=payload.username,
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
            password_changed_at=datetime.now(UTC),
            mfa_required=payload.mfa_required,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        await session.execute(
            insert(user_role),
            [{"user_id": user.id, "role_id": role.id} for role in roles],
        )
        await session.commit()
        return {"id": str(user.id), "username": user.username}


@admin_router.post("/users/{user_id}/{action}", response_model=dict[str, Any])
async def user_state(
    user_id: uuid.UUID,
    action: str,
    request: Request,
    _: UsersWrite,
) -> dict[str, Any]:
    if action not in {"activate", "deactivate"}:
        raise HTTPException(404, "unknown user action")
    async with request.app.state.session_factory() as session:
        user = await session.get(AdminUser, user_id)
        if user is None:
            raise HTTPException(404, "user not found")
        user.is_active = action == "activate"
        if not user.is_active:
            await session.execute(delete(AdminSession).where(AdminSession.user_id == user.id))
        await session.commit()
        return {"id": str(user.id), "is_active": user.is_active}


@admin_router.get("/roles", response_model=list[dict[str, Any]])
async def list_roles(request: Request, _: UsersRead) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        roles = (await session.execute(select(Role).order_by(Role.name))).scalars()
        result = []
        for role in roles:
            codes = list(
                (
                    await session.execute(
                        select(Permission.code)
                        .join(role_permission, role_permission.c.permission_id == Permission.id)
                        .where(role_permission.c.role_id == role.id)
                    )
                ).scalars()
            )
            result.append({"id": str(role.id), "name": role.name, "permissions": sorted(codes)})
        return result


@admin_router.get("/permissions", response_model=list[dict[str, Any]])
async def list_permissions(request: Request, _: UsersRead) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        rows = (await session.execute(select(Permission).order_by(Permission.code))).scalars()
        return [{"code": row.code, "description": row.description} for row in rows]


@admin_router.post("/roles", response_model=dict[str, Any], status_code=201)
async def create_role(payload: RoleRequest, request: Request, _: UsersWrite) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        if (
            await session.execute(select(Role).where(Role.name == payload.name))
        ).scalar_one_or_none():
            raise HTTPException(409, "role already exists")
        permissions = list(
            (
                await session.execute(
                    select(Permission).where(Permission.code.in_(payload.permission_codes))
                )
            ).scalars()
        )
        if len(permissions) != len(set(payload.permission_codes)):
            raise HTTPException(422, "one or more permissions do not exist")
        role = Role(name=payload.name, description=payload.description, is_system=False)
        session.add(role)
        await session.flush()
        await session.execute(
            insert(role_permission),
            [{"role_id": role.id, "permission_id": item.id} for item in permissions],
        )
        await session.commit()
        return {"id": str(role.id), "name": role.name}


@admin_router.put("/roles/{role_id}", response_model=dict[str, Any])
async def update_role(
    role_id: uuid.UUID, payload: RoleRequest, request: Request, _: UsersWrite
) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        role = await session.get(Role, role_id)
        if role is None:
            raise HTTPException(404, "role not found")
        if role.is_system:
            raise HTTPException(409, "built-in roles are immutable")
        permissions = list(
            (
                await session.execute(
                    select(Permission).where(Permission.code.in_(payload.permission_codes))
                )
            ).scalars()
        )
        if len(permissions) != len(set(payload.permission_codes)):
            raise HTTPException(422, "one or more permissions do not exist")
        role.name = payload.name
        role.description = payload.description
        await session.execute(delete(role_permission).where(role_permission.c.role_id == role.id))
        await session.execute(
            insert(role_permission),
            [{"role_id": role.id, "permission_id": item.id} for item in permissions],
        )
        await session.commit()
        return {"id": str(role.id), "name": role.name}


@admin_router.put("/users/{user_id}/roles", response_model=dict[str, Any])
async def assign_user_roles(
    user_id: uuid.UUID,
    payload: RoleAssignmentRequest,
    request: Request,
    _: UsersWrite,
) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        user = await session.get(AdminUser, user_id)
        roles = list(
            (await session.execute(select(Role).where(Role.id.in_(payload.role_ids)))).scalars()
        )
        if user is None:
            raise HTTPException(404, "user not found")
        if len(roles) != len(set(payload.role_ids)):
            raise HTTPException(422, "one or more roles do not exist")
        await session.execute(delete(user_role).where(user_role.c.user_id == user.id))
        await session.execute(
            insert(user_role),
            [{"user_id": user.id, "role_id": role.id} for role in roles],
        )
        await session.execute(delete(AdminSession).where(AdminSession.user_id == user.id))
        await session.commit()
        return {"id": str(user.id), "roles": sorted(role.name for role in roles)}


@admin_router.get("/audit", response_model=list[dict[str, Any]])
async def list_audit(request: Request, _: AuditRead) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        rows = (
            await session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500))
        ).scalars()
        return [
            {
                "id": str(row.id),
                "actor": row.actor_label,
                "action": row.action,
                "resource_type": row.resource_type,
                "outcome": row.outcome,
                "correlation_id": row.correlation_id,
                "details": row.details,
                "created_at": row.created_at,
            }
            for row in rows
        ]


@admin_router.get("/secrets", response_model=list[dict[str, Any]])
async def list_secret_revisions(request: Request, _: UsersRead) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        rows = (
            await session.execute(select(SecretRevision).order_by(SecretRevision.created_at.desc()))
        ).scalars()
        return [
            {
                "id": str(row.id),
                "name": row.name,
                "version": row.version,
                "status": row.status,
                "activated_at": row.activated_at,
                "retire_after": row.retire_after,
            }
            for row in rows
        ]


@admin_router.post("/secrets/rotate", response_model=dict[str, Any], status_code=201)
async def rotate_secret_metadata(
    payload: SecretRotationRequest,
    request: Request,
    _: UsersWrite,
) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        previous = list(
            (
                await session.execute(
                    select(SecretRevision).where(
                        SecretRevision.name == payload.name,
                        SecretRevision.status == "active",
                    )
                )
            ).scalars()
        )
        for item in previous:
            item.status = "overlap"
            item.retire_after = payload.retire_previous_at
        current = SecretRevision(
            name=payload.name,
            version=payload.version,
            status="active",
            activated_at=datetime.now(UTC),
        )
        session.add(current)
        await session.commit()
        return {"id": str(current.id), "status": current.status}
