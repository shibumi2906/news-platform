"""harden integration contract

Revision ID: a6c1e9f42b30
Revises: d5e1f0a3c782
"""

# mypy: ignore-errors
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a6c1e9f42b30"
down_revision: str | None = "d5e1f0a3c782"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _identity_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("canonical_news_package", sa.Column("operation", sa.String(32), server_default="created", nullable=False))
    op.add_column("canonical_news_package", sa.Column("revision_reason", sa.String(2000)))
    for name in ("topics", "categories", "geographies", "ai_provenance"):
        op.add_column("canonical_news_package", sa.Column(name, JSON, server_default=sa.text("'[]'"), nullable=False))

    op.add_column("delivery", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("delivery", sa.Column("dead_lettered_at", sa.DateTime(timezone=True)))
    op.add_column("delivery", sa.Column("last_error", sa.String(255)))
    op.add_column("delivery", sa.Column("manual_retry_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("delivery", sa.Column("attempt_budget_used", sa.Integer(), server_default="0", nullable=False))
    op.create_index("ix_delivery_status_next_attempt", "delivery", ["status", "next_attempt_at"])

    op.add_column("site_connection", sa.Column("active_key_id", sa.String(64), server_default="legacy", nullable=False))
    op.add_column("site_connection", sa.Column("previous_key_id", sa.String(64)))
    op.add_column("site_connection", sa.Column("previous_hmac_secret", sa.String(255)))

    op.add_column("ai_operation_run", sa.Column("ai_config_release_id", sa.Uuid(), sa.ForeignKey("ai_config_release.id")))

    op.create_table(
        "extracted_geography",
        sa.Column("source_material_id", sa.Uuid(), sa.ForeignKey("source_material.id"), nullable=False),
        sa.Column("country", sa.String(255)),
        sa.Column("country_code", sa.String(2)),
        sa.Column("state_or_region", sa.String(255)),
        sa.Column("state_or_region_code", sa.String(64)),
        sa.Column("metro", sa.String(255)),
        sa.Column("city", sa.String(255)),
        sa.Column("district", sa.String(255)),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("ai_operation_run_id", sa.Uuid(), sa.ForeignKey("ai_operation_run.id"), nullable=False),
        *_identity_columns(),
    )
    op.create_index("ix_extracted_geography_material", "extracted_geography", ["source_material_id"])

    op.create_table(
        "integration_audit_event",
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(255)),
        sa.Column("details", JSON, server_default=sa.text("'{}'"), nullable=False),
        *_identity_columns(),
    )
    op.create_index("ix_integration_audit_action_created", "integration_audit_event", ["action", "created_at"])

    op.create_table(
        "replay_request",
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("site_connection.id"), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("from_time", sa.DateTime(timezone=True)),
        sa.Column("to_time", sa.DateTime(timezone=True)),
        sa.Column("package_id", sa.Uuid()),
        sa.Column("min_version", sa.Integer()),
        sa.Column("max_version", sa.Integer()),
        sa.Column("package_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(32), server_default="scheduled", nullable=False),
        *_identity_columns(),
        sa.UniqueConstraint("idempotency_key", name="uq_replay_request_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("replay_request")
    op.drop_index("ix_integration_audit_action_created", table_name="integration_audit_event")
    op.drop_table("integration_audit_event")
    op.drop_index("ix_extracted_geography_material", table_name="extracted_geography")
    op.drop_table("extracted_geography")
    op.drop_column("ai_operation_run", "ai_config_release_id")
    for name in ("previous_hmac_secret", "previous_key_id", "active_key_id"):
        op.drop_column("site_connection", name)
    op.drop_index("ix_delivery_status_next_attempt", table_name="delivery")
    for name in ("attempt_budget_used", "manual_retry_count", "last_error", "dead_lettered_at", "next_attempt_at"):
        op.drop_column("delivery", name)
    for name in ("ai_provenance", "geographies", "categories", "topics", "revision_reason", "operation"):
        op.drop_column("canonical_news_package", name)
