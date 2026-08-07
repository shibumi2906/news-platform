"""harden identity constraints

Revision ID: a84d73c09f21
Revises: f4b7c91d2e10
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a84d73c09f21"
down_revision: str | None = "f4b7c91d2e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_admin_user_email", "admin_user", ["email"])
    op.create_unique_constraint(
        "uq_admin_user_oidc_identity",
        "admin_user",
        ["oidc_issuer", "oidc_subject"],
    )
    op.create_check_constraint(
        "admin_session_idle_before_expiry_check",
        "admin_session",
        "idle_expires_at <= expires_at",
    )
    op.create_check_constraint(
        "secret_revision_status_check",
        "secret_revision",
        "status IN ('active', 'overlap', 'retired')",
    )
    op.create_check_constraint(
        "background_job_attempt_budget_check",
        "background_job",
        "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
    )
    op.create_check_constraint(
        "background_job_attempt_values_check",
        "background_job_attempt",
        "attempt_number > 0 AND latency_ms >= 0",
    )
    op.create_check_constraint(
        "background_job_attempt_status_check",
        "background_job_attempt",
        "status IN ('succeeded', 'retryable_error', 'permanent_error')",
    )
    op.create_check_constraint(
        "dead_letter_replay_count_check", "dead_letter", "replay_count >= 0"
    )
    op.create_check_constraint(
        "distribution_job_attempt_budget_check",
        "distribution_job",
        "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
    )
    op.create_check_constraint(
        "distribution_attempt_values_check",
        "distribution_attempt",
        "attempt_number > 0 AND latency_ms >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "distribution_attempt_values_check", "distribution_attempt", type_="check"
    )
    op.drop_constraint(
        "distribution_job_attempt_budget_check", "distribution_job", type_="check"
    )
    op.drop_constraint("dead_letter_replay_count_check", "dead_letter", type_="check")
    op.drop_constraint(
        "background_job_attempt_status_check", "background_job_attempt", type_="check"
    )
    op.drop_constraint(
        "background_job_attempt_values_check", "background_job_attempt", type_="check"
    )
    op.drop_constraint(
        "background_job_attempt_budget_check", "background_job", type_="check"
    )
    op.drop_constraint("secret_revision_status_check", "secret_revision", type_="check")
    op.drop_constraint(
        "admin_session_idle_before_expiry_check", "admin_session", type_="check"
    )
    op.drop_constraint("uq_admin_user_oidc_identity", "admin_user", type_="unique")
    op.drop_constraint("uq_admin_user_email", "admin_user", type_="unique")
