"""add HTML source configuration

Revision ID: d91a4f0b5c72
Revises: 8c4e7a19d5b0
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d91a4f0b5c72"
down_revision: str | None = "8c4e7a19d5b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source",
        sa.Column(
            "config",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("source", "config")
