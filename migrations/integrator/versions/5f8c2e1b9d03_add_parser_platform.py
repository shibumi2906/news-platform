"""add parser platform

Revision ID: 5f8c2e1b9d03
Revises: 0e91c4b7d5a2
"""
# ruff: noqa: I001,E501

from alembic import op
import sqlalchemy as sa

revision = "5f8c2e1b9d03"
down_revision = "0e91c4b7d5a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("parser_snapshot", sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source.id"), nullable=False), sa.Column("url", sa.String(2048), nullable=False), sa.Column("kind", sa.String(32), nullable=False), sa.Column("html", sa.Text(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("parser_version", sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source.id"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("adapter_type", sa.String(32), nullable=False), sa.Column("rules", sa.JSON(), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("parent_version_id", sa.Uuid(), sa.ForeignKey("parser_version.id")), sa.Column("snapshot_id", sa.Uuid(), sa.ForeignKey("parser_snapshot.id")), sa.Column("reason", sa.String(1000)), sa.Column("validation_report", sa.JSON(), nullable=False), sa.Column("reviewed_by_actor_id", sa.String(255)), sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("source_id", "version", name="uq_parser_version"))
    op.create_table("parser_repair", sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source.id"), nullable=False), sa.Column("detected_version_id", sa.Uuid(), sa.ForeignKey("parser_version.id")), sa.Column("proposed_version_id", sa.Uuid(), sa.ForeignKey("parser_version.id")), sa.Column("status", sa.String(32), nullable=False), sa.Column("reason", sa.String(1000), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("parser_repair")
    op.drop_table("parser_version")
    op.drop_table("parser_snapshot")
