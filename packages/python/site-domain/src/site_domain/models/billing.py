"""Provider-neutral, tenant-scoped billing records. Card data is never stored."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class BillingCustomer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "billing_customer"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", "provider_customer_id", name="uq_billing_customer_provider"
        ),
        CheckConstraint("status IN ('active', 'archived')", name="billing_customer_status"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    provider: Mapped[str | None] = mapped_column(String(64), default=None)
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), default=None)
    email: Mapped[str | None] = mapped_column(String(320), default=None)
    status: Mapped[str] = mapped_column(String(32), default="active")
    attributes: Mapped[dict[str, Any]] = mapped_column("metadata", PortableJSON, default=dict)


class BillingInvoice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "billing_invoice"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_billing_invoice_key"),
        CheckConstraint("amount_minor > 0", name="billing_invoice_amount"),
        CheckConstraint(
            "status IN ('draft', 'open', 'paid', 'void', 'cancelled')",
            name="billing_invoice_status",
        ),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("billing_customer.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    idempotency_key: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str | None] = mapped_column(String(64), default=None)
    provider_reference: Mapped[str | None] = mapped_column(String(255), default=None)


class BillingPayment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "billing_payment"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", "provider_reference", name="uq_billing_payment_provider"
        ),
        CheckConstraint("amount_minor > 0", name="billing_payment_amount"),
        CheckConstraint(
            "status IN ('pending', 'authorized', 'succeeded', 'failed', 'cancelled', 'refunded')",
            name="billing_payment_status",
        ),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("billing_invoice.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    provider: Mapped[str | None] = mapped_column(String(64), default=None)
    provider_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    provider_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class BillingWebhookEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "billing_webhook_event"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_billing_webhook_provider_event"),
    )
    provider: Mapped[str] = mapped_column(String(64))
    provider_event_id: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="received")


class BillingAuditEntry(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "billing_audit_entry"
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    aggregate_type: Mapped[str] = mapped_column(String(32))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
