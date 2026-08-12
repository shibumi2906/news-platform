"""Site-owned Dashboard outbox and export attempt audit."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class DashboardOutbox(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "dashboard_outbox"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_dashboard_outbox_idempotency"),
        CheckConstraint(
            "status IN ('scheduled', 'processing', 'retry_wait', 'exported', 'failed')",
            name="dashboard_outbox_status_check",
        ),
    )

    event_type: Mapped[str] = mapped_column(String(128))
    metric: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    dimensions: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    value: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)


class DashboardExportAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "dashboard_export_attempt"
    __table_args__ = (
        UniqueConstraint("outbox_id", "attempt_number", name="uq_dashboard_attempt_number"),
    )

    outbox_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboard_outbox.id", ondelete="CASCADE")
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    response_status: Mapped[int | None] = mapped_column(Integer, default=None)
    diagnostics: Mapped[str | None] = mapped_column(Text, default=None)
