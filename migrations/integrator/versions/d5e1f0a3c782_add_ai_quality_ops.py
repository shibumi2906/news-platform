"""add ai quality operations

Revision ID: d5e1f0a3c782
Revises: c4d0e9a2b672
"""
# ruff: noqa
# ruff: noqa: E501
import sqlalchemy as sa
from alembic import op

revision = "d5e1f0a3c782"
down_revision = "c4d0e9a2b672"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("ai_eval_set", sa.Column("operation", sa.String(64), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("cases", sa.JSON(), nullable=False), sa.Column("frozen", sa.Boolean(), nullable=False), sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_table("ai_quality_policy", sa.Column("operation", sa.String(64), unique=True, nullable=False), sa.Column("minimum_score", sa.Float(), nullable=False), sa.Column("canary_percent", sa.Integer(), nullable=False), sa.Column("budget_usd", sa.Float(), nullable=False), sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_table("ai_config_release", sa.Column("prompt_version_id", sa.Uuid(), sa.ForeignKey("prompt_version.id"), nullable=False), sa.Column("provider", sa.String(64), nullable=False), sa.Column("model", sa.String(128), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("eval_score", sa.Float()), sa.Column("rollout_percent", sa.Integer(), nullable=False), sa.Column("previous_release_id", sa.Uuid(), sa.ForeignKey("ai_config_release.id")), sa.Column("audit", sa.JSON(), nullable=False), sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))

def downgrade() -> None:
    op.drop_table("ai_config_release"); op.drop_table("ai_quality_policy"); op.drop_table("ai_eval_set")
