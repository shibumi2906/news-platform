"""add source health

Revision ID: c4d0e9a2b671
Revises: 5f8c2e1b9d03
"""
# ruff: noqa: E501
import sqlalchemy as sa
from alembic import op

revision = "c4d0e9a2b671"
down_revision = "5f8c2e1b9d03"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("source", sa.Column("health_status", sa.String(32), server_default="healthy", nullable=False))
    op.add_column("source", sa.Column("health_reason", sa.String(1000)))
    op.add_column("source", sa.Column("last_success_at", sa.DateTime(timezone=True)))
    op.add_column("source", sa.Column("next_retry_at", sa.DateTime(timezone=True)))
    op.create_table("source_state_audit", sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source.id"), nullable=False), sa.Column("previous_status", sa.String(32)), sa.Column("status", sa.String(32), nullable=False), sa.Column("reason", sa.String(1000)), sa.Column("diagnostics", sa.JSON(), nullable=False), sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))

def downgrade() -> None:
    op.drop_table("source_state_audit")
    op.drop_column("source", "next_retry_at")
    op.drop_column("source", "last_success_at")
    op.drop_column("source", "health_reason")
    op.drop_column("source", "health_status")
