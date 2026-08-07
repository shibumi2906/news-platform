"""Provider-neutral background jobs, attempts, leases, and dead letters."""

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


class UnifiedJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "background_job"
    __table_args__ = (
        UniqueConstraint("queue", "idempotency_key", name="uq_background_job_idempotency"),
        CheckConstraint(
            "status IN ('scheduled', 'processing', 'retry_wait', 'succeeded', "
            "'failed', 'dlq', 'cancelled')",
            name="background_job_status_check",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
            name="background_job_attempt_budget_check",
        ),
    )

    queue: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    lease_owner: Mapped[str | None] = mapped_column(String(128), default=None)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    error_message: Mapped[str | None] = mapped_column(String(512), default=None)
    correlation_id: Mapped[str | None] = mapped_column(String(64), default=None)


class UnifiedJobAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "background_job_attempt"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_number", name="uq_background_job_attempt_number"),
        CheckConstraint(
            "attempt_number > 0 AND latency_ms >= 0",
            name="background_job_attempt_values_check",
        ),
        CheckConstraint(
            "status IN ('succeeded', 'retryable_error', 'permanent_error')",
            name="background_job_attempt_status_check",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("background_job.id", ondelete="CASCADE"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    diagnostics: Mapped[str | None] = mapped_column(Text, default=None)


class DeadLetter(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "dead_letter"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_dead_letter_job"),
        CheckConstraint("replay_count >= 0", name="dead_letter_replay_count_check"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("background_job.id", ondelete="CASCADE"))
    reason_code: Mapped[str] = mapped_column(String(64))
    diagnostics: Mapped[str] = mapped_column(Text)
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
