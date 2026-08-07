"""Local installation identity, RBAC, sessions, audit, and secret metadata."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

user_role = Table(
    "user_role",
    Base.metadata,
    Column("user_id", ForeignKey("admin_user.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
)
role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True),
)


class AdminUser(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "admin_user"
    __table_args__ = (
        UniqueConstraint("email", name="uq_admin_user_email"),
        UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_admin_user_oidc_identity"),
    )

    username: Mapped[str] = mapped_column(String(128), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(512), default=None)
    display_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    oidc_issuer: Mapped[str | None] = mapped_column(String(512), default=None)
    oidc_subject: Mapped[str | None] = mapped_column(String(512), default=None)
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_method: Mapped[str | None] = mapped_column(String(32), default=None)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "role"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(String(512), default=None)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class Permission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "permission"

    code: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(String(512), default=None)


class AdminSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "admin_session"
    __table_args__ = (
        CheckConstraint(
            "idle_expires_at <= expires_at", name="admin_session_idle_before_expiry_check"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin_user.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    auth_method: Mapped[str] = mapped_column(String(32))
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_log"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    actor_label: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(255))
    resource_type: Mapped[str] = mapped_column(String(128))
    resource_id: Mapped[str | None] = mapped_column(String(255), default=None)
    outcome: Mapped[str] = mapped_column(String(32))
    correlation_id: Mapped[str | None] = mapped_column(String(64), default=None)
    details: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SecretRevision(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "secret_revision"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_secret_revision"),
        CheckConstraint(
            "status IN ('active', 'overlap', 'retired')",
            name="secret_revision_status_check",
        ),
    )

    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    retire_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
