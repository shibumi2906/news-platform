"""add editorial workflow tables

Revision ID: 7b1c9d34e1fa
Revises: eac8eb75bddc
"""
# mypy: ignore-errors

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7b1c9d34e1fa"
down_revision: str | None = "eac8eb75bddc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "site_article",
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("latest_version_number", sa.Integer(), nullable=False),
        sa.Column("four_eyes_required", sa.Boolean(), nullable=False),
        *_id_columns(),
    )
    op.create_table(
        "article_version",
        sa.Column("article_id", sa.Uuid(), sa.ForeignKey("site_article.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "content", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_by_actor_id", sa.String(255), nullable=False),
        sa.Column(
            "based_on_incoming_package_version_id",
            sa.Uuid(),
            sa.ForeignKey("incoming_package_version.id"),
        ),
        *_id_columns(),
        sa.UniqueConstraint("article_id", "version_number", name="uq_article_version_number"),
    )
    op.create_table(
        "article_source_link",
        sa.Column("article_id", sa.Uuid(), sa.ForeignKey("site_article.id"), nullable=False),
        sa.Column(
            "incoming_package_id", sa.Uuid(), sa.ForeignKey("incoming_package.id"), nullable=False
        ),
        sa.Column("last_merged_package_version", sa.Integer(), nullable=False),
        *_id_columns(),
        sa.UniqueConstraint("article_id", "incoming_package_id", name="uq_article_source_link"),
    )
    op.create_table(
        "editorial_task",
        sa.Column("article_id", sa.Uuid(), sa.ForeignKey("site_article.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assigned_actor_id", sa.String(255)),
        sa.Column("reason", sa.String(1000)),
        *_id_columns(),
    )
    op.create_table(
        "review_decision",
        sa.Column("article_id", sa.Uuid(), sa.ForeignKey("site_article.id"), nullable=False),
        sa.Column(
            "article_version_id", sa.Uuid(), sa.ForeignKey("article_version.id"), nullable=False
        ),
        sa.Column("reviewer_actor_id", sa.String(255), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(1000)),
        *_id_columns(),
    )
    op.create_table(
        "publication",
        sa.Column("article_id", sa.Uuid(), sa.ForeignKey("site_article.id"), nullable=False),
        sa.Column("active_article_version_id", sa.Uuid(), sa.ForeignKey("article_version.id")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("unpublished_at", sa.DateTime(timezone=True)),
        *_id_columns(),
        sa.UniqueConstraint("article_id", name="uq_publication_article"),
    )
    op.create_table(
        "correction_notice",
        sa.Column("article_id", sa.Uuid(), sa.ForeignKey("site_article.id"), nullable=False),
        sa.Column(
            "article_version_id", sa.Uuid(), sa.ForeignKey("article_version.id"), nullable=False
        ),
        sa.Column("explanation", sa.String(2000), nullable=False),
        *_id_columns(),
    )


def downgrade() -> None:
    for table in (
        "correction_notice",
        "publication",
        "review_decision",
        "editorial_task",
        "article_source_link",
        "article_version",
        "site_article",
    ):
        op.drop_table(table)
