"""Add site entity projections for public entity pages."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a43f0d92be14"
down_revision = "d2f0a79c4e31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_entity",
        sa.Column("name", sa.String(length=1024), nullable=False),
        sa.Column("normalized_name", sa.String(length=1024), nullable=False),
        sa.Column("kind", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "normalized_name", name="uq_site_entity_kind_normalized_name"),
    )
    op.create_table(
        "article_version_entity",
        sa.Column("article_version_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["article_version_id"], ["article_version.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["site_entity.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "article_version_id", "entity_id", name="uq_article_version_entity_association"
        ),
    )


def downgrade() -> None:
    op.drop_table("article_version_entity")
    op.drop_table("site_entity")
