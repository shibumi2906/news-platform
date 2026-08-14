"""Add site event projection for public timelines."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d2f0a79c4e31"
down_revision = "c1d8e82a4f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_event",
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("taxonomy", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_event_id"),
    )
    op.add_column("article_version", sa.Column("event_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_article_version_event_id_site_event",
        "article_version",
        "site_event",
        ["event_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_article_version_event_id_site_event", "article_version", type_="foreignkey"
    )
    op.drop_column("article_version", "event_id")
    op.drop_table("site_event")
