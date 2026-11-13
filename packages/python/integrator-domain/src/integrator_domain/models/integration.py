"""Auditable integration control-plane requests."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class IntegrationAuditEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "integration_audit_event"
    __table_args__ = (Index("ix_integration_audit_action_created", "action", "created_at"),)

    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(255), default=None)
    details: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class ReplayRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "replay_request"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_replay_request_idempotency"),
    )

    idempotency_key: Mapped[str] = mapped_column(String(255))
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_connection.id"))
    requested_by: Mapped[str] = mapped_column(String(255))
    from_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    to_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    package_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    min_version: Mapped[int | None] = mapped_column(Integer, default=None)
    max_version: Mapped[int | None] = mapped_column(Integer, default=None)
    package_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
