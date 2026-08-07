"""Local IAM bootstrap, login sessions, permission resolution, and audit writes."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from common.auth import AuthContext
from common.logging import get_correlation_id, get_logger
from common.security import (
    Principal,
    PrincipalSigner,
    csrf_hash,
    hash_password,
    token_hash,
    verify_password,
)
from common.time import as_utc
from site_domain.models import (
    AdminSession,
    AdminUser,
    AuditLog,
    Permission,
    Role,
    role_permission,
    user_role,
)
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)
_DUMMY_PASSWORD_HASH = hash_password(
    "timing-equalization-only", salt=b"\x00" * 16
)

PERMISSIONS: dict[str, str] = {
    "users:read": "View users and roles",
    "users:write": "Manage users and role assignments",
    "audit:read": "View immutable audit records",
    "system:read": "View health, metrics, and alerts",
    "jobs:manage": "Inspect and replay failed jobs",
    "articles:read": "View editorial records",
    "articles:write": "Create, review, and publish article versions",
    "media:manage": "Manage media and generation",
    "distribution:manage": "Manage channels and distribution jobs",
    "sources:manage": "Manage source ingestion",
    "topics:manage": "Manage AI topics and language configuration",
}
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "Administrator": set(PERMISSIONS),
    "Editor": {"articles:read", "articles:write", "media:manage", "distribution:manage"},
    "Operator": {"system:read", "jobs:manage", "sources:manage"},
    "Viewer": {"articles:read", "audit:read", "system:read"},
}


async def ensure_security_seed(
    session: AsyncSession, *, username: str | None, password: str | None
) -> None:
    permissions: dict[str, Permission] = {}
    for code, description in PERMISSIONS.items():
        item = (
            await session.execute(select(Permission).where(Permission.code == code))
        ).scalar_one_or_none()
        if item is None:
            item = Permission(code=code, description=description)
            session.add(item)
            await session.flush()
        elif item.description != description:
            item.description = description
        permissions[code] = item
    roles: dict[str, Role] = {}
    for name, codes in ROLE_PERMISSIONS.items():
        role = (await session.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
        if role is None:
            role = Role(name=name, description=f"Built-in {name.lower()} role", is_system=True)
            session.add(role)
            await session.flush()
            current_codes: set[str] = set()
        else:
            current_codes = set(
                (
                    await session.execute(
                        select(Permission.code)
                        .join(
                            role_permission,
                            role_permission.c.permission_id == Permission.id,
                        )
                        .where(role_permission.c.role_id == role.id)
                    )
                ).scalars()
            )
        if current_codes != codes:
            affected_user_ids = list(
                (
                    await session.execute(
                        select(user_role.c.user_id).where(user_role.c.role_id == role.id)
                    )
                ).scalars()
            )
            await session.execute(
                delete(role_permission).where(role_permission.c.role_id == role.id)
            )
            await session.execute(
                insert(role_permission),
                [{"role_id": role.id, "permission_id": permissions[code].id} for code in codes],
            )
            if affected_user_ids:
                await session.execute(
                    update(AdminSession)
                    .where(
                        AdminSession.user_id.in_(affected_user_ids),
                        AdminSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=datetime.now(UTC))
                )
        roles[name] = role
    if username and password:
        user = (
            await session.execute(select(AdminUser).where(AdminUser.username == username))
        ).scalar_one_or_none()
        if user is None:
            now = datetime.now(UTC)
            user = AdminUser(
                username=username,
                display_name=username,
                password_hash=hash_password(password),
                password_changed_at=now,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            await session.execute(
                insert(user_role).values(user_id=user.id, role_id=roles["Administrator"].id)
            )
            logger.info("bootstrap_admin_created", user_id=str(user.id))
    await session.commit()


async def login(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    signer: PrincipalSigner,
    ttl_seconds: int,
    idle_seconds: int,
) -> tuple[str, str, AdminUser, set[str]]:
    user = (
        await session.execute(select(AdminUser).where(AdminUser.username == username))
    ).scalar_one_or_none()
    candidate_hash = user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(password, candidate_hash)
    if (
        user is None
        or not user.is_active
        or user.password_hash is None
        or not password_valid
    ):
        raise PermissionError("invalid credentials")
    if user.mfa_required:
        raise PermissionError("mfa challenge required")
    permissions = await permissions_for_user(session, user.id)
    now = datetime.now(UTC)
    session_row = AdminSession(
        user_id=user.id,
        token_hash="pending",
        csrf_token_hash="pending",
        expires_at=now + timedelta(seconds=ttl_seconds),
        idle_expires_at=now + timedelta(seconds=idle_seconds),
        last_seen_at=now,
        auth_method="password",
        mfa_verified=not user.mfa_required,
    )
    session.add(session_row)
    await session.flush()
    token = signer.issue(
        session_id=session_row.id,
        user_id=user.id,
        actor=user.username,
        permissions=permissions,
        ttl_seconds=ttl_seconds,
        mfa_verified=session_row.mfa_verified,
        auth_method="password",
    )
    csrf_token = secrets.token_urlsafe(32)
    session_row.token_hash = token_hash(token)
    session_row.csrf_token_hash = csrf_hash(csrf_token)
    await session.commit()
    return token, csrf_token, user, permissions


async def permissions_for_user(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = await session.execute(
        select(Permission.code)
        .join(role_permission, role_permission.c.permission_id == Permission.id)
        .join(user_role, user_role.c.role_id == role_permission.c.role_id)
        .where(user_role.c.user_id == user_id)
    )
    return set(rows.scalars())


def build_session_validator(
    factory: async_sessionmaker[AsyncSession], *, idle_seconds: int
) -> object:
    async def validate(
        principal: Principal, token: str, csrf_token: str | None, unsafe: bool
    ) -> bool:
        async with factory() as session:
            row = await session.get(AdminSession, principal.session_id)
            user = await session.get(AdminUser, principal.user_id)
            now = datetime.now(UTC)
            if (
                row is None
                or user is None
                or not user.is_active
                or row.revoked_at is not None
                or as_utc(row.expires_at) <= now
                or as_utc(row.idle_expires_at) <= now
                or not secrets.compare_digest(row.token_hash, token_hash(token))
            ):
                return False
            if unsafe and (
                csrf_token is None
                or not secrets.compare_digest(row.csrf_token_hash, csrf_hash(csrf_token))
            ):
                return False
            row.last_seen_at = now
            row.idle_expires_at = min(as_utc(row.expires_at), now + timedelta(seconds=idle_seconds))
            await session.commit()
            return True

    return validate


async def write_audit(
    factory: async_sessionmaker[AsyncSession],
    *,
    context: AuthContext,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str,
    status_code: int,
) -> None:
    async with factory() as session:
        session.add(
            AuditLog(
                actor_user_id=uuid.UUID(context.user_id) if context.user_id else None,
                actor_label=context.actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                correlation_id=get_correlation_id(),
                details={"status_code": status_code, "auth_method": context.auth_method},
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
