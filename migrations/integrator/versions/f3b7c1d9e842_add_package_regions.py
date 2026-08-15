"""persist configured regions on canonical packages.

Revision ID: f3b7c1d9e842
Revises: d91a4f0b5c72
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3b7c1d9e842"
down_revision: str | None = "d91a4f0b5c72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "canonical_news_package",
        sa.Column(
            "regions",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("canonical_news_package", "regions")
