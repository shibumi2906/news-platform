"""Distribution channels and idempotent delivery jobs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class DistributionChannel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "distribution_channel"
    __table_args__ = (
        UniqueConstraint("kind", "account_key", name="uq_distribution_channel_account"),
    )

    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32))
    account_key: Mapped[str] = mapped_column(String(255))
    credential_ref: Mapped[str | None] = mapped_column(String(255), default=None)
    config: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DistributionJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "distribution_job"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_distribution_job_idempotency"),
        CheckConstraint(
            "status IN ('scheduled', 'processing', 'retry_wait', 'delivered', "
            "'failed', 'dlq', 'cancelled')",
            name="distribution_job_status_check",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
            name="distribution_job_attempt_budget_check",
        ),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("distribution_channel.id"))
    unified_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("background_job.id"), unique=True, default=None
    )
    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_version.id"))
    translation_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("article_translation_version.id"), default=None
    )
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_asset.id"), default=None
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
    external_publication_id: Mapped[str | None] = mapped_column(String(255), default=None)
    external_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    error_message: Mapped[str | None] = mapped_column(String(512), default=None)
    lease_owner: Mapped[str | None] = mapped_column(String(128), default=None)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class DistributionAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "distribution_attempt"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_number", name="uq_distribution_attempt_number"),
        CheckConstraint(
            "status IN ('succeeded', 'retryable_error', 'permanent_error')",
            name="distribution_attempt_status_check",
        ),
        CheckConstraint(
            "attempt_number > 0 AND latency_ms >= 0",
            name="distribution_attempt_values_check",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("distribution_job.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    provider_request_id: Mapped[str | None] = mapped_column(String(255), default=None)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    diagnostics: Mapped[str | None] = mapped_column(Text, default=None)
