"""add article translations

Revision ID: a317f4c92e60
Revises: 7b1c9d34e1fa
"""

# mypy: ignore-errors
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a317f4c92e60"
down_revision: str | None = "7b1c9d34e1fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_translation_version",
        sa.Column("article_version_id", sa.Uuid(), sa.ForeignKey("article_version.id"), nullable=False),
        sa.Column("source_language_code", sa.String(16), nullable=False),
        sa.Column("language_code", sa.String(16), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("content", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "article_version_id", "language_code", name="uq_article_translation_language"
        ),
        sa.CheckConstraint("direction IN ('ltr', 'rtl')"),
    )


def downgrade() -> None:
    op.drop_table("article_translation_version")
