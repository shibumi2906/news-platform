"""Tenant-scoped advertising inventory and immutable delivery events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class Advertiser(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "advertiser"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_advertiser_tenant_name"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")


class AdPlacement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ad_placement"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_ad_placement_code"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    code: Mapped[str] = mapped_column(String(64))
    allowed_kinds: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AdCampaign(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ad_campaign"
    __table_args__ = (
        CheckConstraint("budget_minor IS NULL OR budget_minor > 0", name="ad_campaign_budget"),
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed', 'cancelled')",
            name="ad_campaign_status",
        ),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("advertiser.id"))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    budget_minor: Mapped[int | None] = mapped_column(Integer, default=None)
    impression_limit: Mapped[int | None] = mapped_column(Integer, default=None)
    click_limit: Mapped[int | None] = mapped_column(Integer, default=None)
    targeting: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AdCreative(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ad_creative"
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_campaign.id"))
    placement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_placement.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    locale: Mapped[str | None] = mapped_column(String(16), default=None)
    destination_url: Mapped[str] = mapped_column(String(2048))
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    rights_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    disclosure: Mapped[str] = mapped_column(String(255), default="Sponsored")


class AdDeliveryEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ad_delivery_event"
    __table_args__ = (UniqueConstraint("tenant_id", "event_id", name="uq_ad_delivery_event"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_id: Mapped[str] = mapped_column(String(128))
    creative_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_creative.id"))
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_campaign.id"))
    placement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_placement.id"))
    event_type: Mapped[str] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
