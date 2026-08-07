"""add unified jobs and dlq

Revision ID: f4b7c91d2e10
Revises: e031a255c1b8
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4b7c91d2e10"
down_revision: str | None = "e031a255c1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_audit_log_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_append_only
          BEFORE UPDATE OR DELETE ON audit_log
          FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
        """
    )
    op.create_table(
        "background_job",
        sa.Column("queue", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('scheduled', 'processing', 'retry_wait', 'succeeded', "
            "'failed', 'dlq', 'cancelled')"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("queue", "idempotency_key", name="uq_background_job_idempotency"),
    )
    op.create_table(
        "background_job_attempt",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("diagnostics", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["job_id"], ["background_job.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_background_job_attempt_number"),
    )
    op.create_table(
        "dead_letter",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("diagnostics", sa.Text(), nullable=False),
        sa.Column("replay_count", sa.Integer(), nullable=False),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["job_id"], ["background_job.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_dead_letter_job"),
    )
    op.add_column("distribution_job", sa.Column("unified_job_id", sa.Uuid(), nullable=True))
    op.add_column(
        "distribution_job", sa.Column("lease_owner", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "distribution_job", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_distribution_job_unified_job",
        "distribution_job",
        "background_job",
        ["unified_job_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_distribution_job_unified_job_id", "distribution_job", ["unified_job_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_distribution_job_unified_job_id", "distribution_job", type_="unique")
    op.drop_constraint("fk_distribution_job_unified_job", "distribution_job", type_="foreignkey")
    op.drop_column("distribution_job", "lease_expires_at")
    op.drop_column("distribution_job", "lease_owner")
    op.drop_column("distribution_job", "unified_job_id")
    op.drop_table("dead_letter")
    op.drop_table("background_job_attempt")
    op.drop_table("background_job")
    op.execute("DROP TRIGGER audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION reject_audit_log_mutation()")
