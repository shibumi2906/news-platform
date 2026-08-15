"""add semantic event intelligence state.

Revision ID: 0e91c4b7d5a2
Revises: f3b7c1d9e842
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0e91c4b7d5a2"
down_revision: str | None = "f3b7c1d9e842"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.drop_constraint("uq_event_source_material", "event", type_="unique")
    op.drop_constraint("uq_event_cluster_key", "event", type_="unique")
    op.alter_column("event", "source_material_id", nullable=True)
    op.add_column("event", sa.Column("status", sa.String(32), server_default="active", nullable=False))
    op.add_column("event", sa.Column("merged_into_event_id", sa.Uuid(), sa.ForeignKey("event.id")))
    op.add_column("event_material", sa.Column("decision", sa.String(32), server_default="separate", nullable=False))
    op.add_column("event_material", sa.Column("evidence", JSON, server_default=sa.text("'{}'"), nullable=False))
    op.create_table(
        "event_clustering_policy",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("auto_merge_threshold", sa.Float(), server_default="0.88", nullable=False),
        sa.Column("review_threshold", sa.Float(), server_default="0.65", nullable=False),
        sa.Column("candidate_window_hours", sa.Integer(), server_default="168", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "event_match_review",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_material_id", sa.Uuid(), sa.ForeignKey("source_material.id"), nullable=False),
        sa.Column("proposed_event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("candidate_event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("evidence", JSON, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("resolved_by_actor_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_material_id", "candidate_event_id", name="uq_event_review_candidate"),
    )
    op.create_table(
        "event_cluster_operation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("target_event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), sa.ForeignKey("event.id")),
        sa.Column("actor_id", sa.String(255)),
        sa.Column("payload", JSON, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("event_cluster_operation")
    op.drop_table("event_match_review")
    op.drop_table("event_clustering_policy")
    op.drop_column("event_material", "evidence")
    op.drop_column("event_material", "decision")
    op.drop_column("event", "merged_into_event_id")
    op.drop_column("event", "status")
    op.alter_column("event", "source_material_id", nullable=False)
    op.create_unique_constraint("uq_event_cluster_key", "event", ["cluster_key"])
    op.create_unique_constraint("uq_event_source_material", "event", ["source_material_id"])
