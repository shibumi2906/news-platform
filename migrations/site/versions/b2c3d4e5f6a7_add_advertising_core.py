"""add advertising core

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advertiser",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_advertiser_tenant_name"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_advertiser_tenant", "advertiser", ["tenant_id"])
    op.create_table(
        "ad_placement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("allowed_kinds", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_ad_placement_code"),
    )
    op.create_index("ix_ad_placement_tenant", "ad_placement", ["tenant_id"])
    op.create_table(
        "ad_campaign",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("advertiser_id", sa.Uuid(), sa.ForeignKey("advertiser.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("budget_minor", sa.Integer()),
        sa.Column("impression_limit", sa.Integer()),
        sa.Column("click_limit", sa.Integer()),
        sa.Column("targeting", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed', 'cancelled')",
            name="ad_campaign_status",
        ),
        sa.CheckConstraint("budget_minor IS NULL OR budget_minor > 0", name="ad_campaign_budget"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ad_campaign_tenant_status", "ad_campaign", ["tenant_id", "status"])
    op.create_table(
        "ad_creative",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("ad_campaign.id"), nullable=False),
        sa.Column("placement_id", sa.Uuid(), sa.ForeignKey("ad_placement.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("locale", sa.String(16)),
        sa.Column("destination_url", sa.String(2048), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("rights_expires_at", sa.DateTime(timezone=True)),
        sa.Column("disclosure", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ad_creative_tenant_campaign", "ad_creative", ["tenant_id", "campaign_id"])
    op.create_table(
        "ad_delivery_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("creative_id", sa.Uuid(), sa.ForeignKey("ad_creative.id"), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("ad_campaign.id"), nullable=False),
        sa.Column("placement_id", sa.Uuid(), sa.ForeignKey("ad_placement.id"), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "event_id", name="uq_ad_delivery_event"),
    )
    op.create_index(
        "ix_ad_delivery_tenant_campaign", "ad_delivery_event", ["tenant_id", "campaign_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ad_delivery_tenant_campaign", table_name="ad_delivery_event")
    op.drop_table("ad_delivery_event")
    op.drop_table("ad_creative")
    op.drop_table("ad_campaign")
    op.drop_table("ad_placement")
    op.drop_table("advertiser")
