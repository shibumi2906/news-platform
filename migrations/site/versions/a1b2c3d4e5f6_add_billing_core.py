"""add provider-neutral billing core

Revision ID: a1b2c3d4e5f6
Revises: a43f0d92be14, a84d73c09f21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: tuple[str, str] = ("a43f0d92be14", "a84d73c09f21")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_customer",
        sa.Column("tenant_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("provider", sa.String(64)),
        sa.Column("provider_customer_id", sa.String(255)),
        sa.Column("email", sa.String(320)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "provider", "provider_customer_id", name="uq_billing_customer_provider"
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="billing_customer_status"),
    )
    op.create_table(
        "billing_invoice",
        sa.Column("tenant_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("billing_customer.id"), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("provider_reference", sa.String(255)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount_minor > 0", name="billing_invoice_amount"),
        sa.CheckConstraint(
            "status IN ('draft', 'open', 'paid', 'void', 'cancelled')",
            name="billing_invoice_status",
        ),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_billing_invoice_key"),
    )
    op.create_table(
        "billing_payment",
        sa.Column("tenant_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("invoice_id", sa.Uuid(), sa.ForeignKey("billing_invoice.id"), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("provider_reference", sa.String(255)),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount_minor > 0", name="billing_payment_amount"),
        sa.CheckConstraint(
            "status IN ('pending', 'authorized', 'succeeded', 'failed', 'cancelled', 'refunded')",
            name="billing_payment_status",
        ),
        sa.UniqueConstraint(
            "tenant_id", "provider", "provider_reference", name="uq_billing_payment_provider"
        ),
    )
    op.create_table(
        "billing_audit_entry",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_type", sa.String(32), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
    )
    op.create_table(
        "billing_webhook_event",
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_billing_webhook_provider_event"
        ),
    )


def downgrade() -> None:
    op.drop_table("billing_audit_entry")
    op.drop_table("billing_webhook_event")
    op.drop_table("billing_payment")
    op.drop_table("billing_invoice")
    op.drop_table("billing_customer")
