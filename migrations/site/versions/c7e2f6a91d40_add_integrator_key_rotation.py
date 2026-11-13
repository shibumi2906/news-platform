"""add integrator key rotation

Revision ID: c7e2f6a91d40
Revises: b2c3d4e5f6a7
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e2f6a91d40"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("integrator_connection", sa.Column("active_key_id", sa.String(64), server_default="legacy", nullable=False))
    op.add_column("integrator_connection", sa.Column("previous_key_id", sa.String(64)))
    op.add_column("integrator_connection", sa.Column("previous_hmac_secret", sa.String(255)))


def downgrade() -> None:
    op.drop_column("integrator_connection", "previous_hmac_secret")
    op.drop_column("integrator_connection", "previous_key_id")
    op.drop_column("integrator_connection", "active_key_id")
