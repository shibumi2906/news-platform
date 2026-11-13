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
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class Advertiser(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "advertiser"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_advertiser_tenant_name"),
        Index("ix_advertiser_tenant", "tenant_id"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")


class AdPlacement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ad_placement"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_ad_placement_code"),
        Index("ix_ad_placement_tenant", "tenant_id"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    code: Mapped[str] = mapped_column(String(64))
    allowed_kinds: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AdCampaign(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ad_campaign"
    __table_args__ = (
        Index("ix_ad_campaign_tenant_status", "tenant_id", "status"),
        CheckConstraint("budget_minor IS NULL OR budget_minor > 0", name="ad_campaign_budget"),
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed', 'cancelled')",
            name="ad_campaign_status",
        ),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column()
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
    __table_args__ = (Index("ix_ad_creative_tenant_campaign", "tenant_id", "campaign_id"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_campaign.id"))
    placement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_placement.id"))
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
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id", name="uq_ad_delivery_event"),
        Index("ix_ad_delivery_tenant_campaign", "tenant_id", "campaign_id"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    event_id: Mapped[str] = mapped_column(String(128))
    creative_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_creative.id"))
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_campaign.id"))
    placement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ad_placement.id"))
    event_type: Mapped[str] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
