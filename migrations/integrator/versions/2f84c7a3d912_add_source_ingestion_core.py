"""add source ingestion core

Revision ID: 2f84c7a3d912
Revises: 4f3328483b27
"""

# mypy: ignore-errors
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2f84c7a3d912"
down_revision: str | None = "4f3328483b27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source", sa.Column("adapter_type", sa.String(32), server_default="rss", nullable=False)
    )
    op.add_column(
        "source",
        sa.Column("poll_interval_seconds", sa.Integer(), server_default="300", nullable=False),
    )
    op.add_column(
        "source", sa.Column("status", sa.String(32), server_default="active", nullable=False)
    )
    op.add_column("source", sa.Column("etag", sa.String(1024)))
    op.add_column("source", sa.Column("last_modified", sa.String(1024)))
    op.add_column("source", sa.Column("last_error", sa.String(1000)))
    op.add_column(
        "source",
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "source_snapshot",
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("body", sa.String()),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("etag", sa.String(1024)),
        sa.Column("last_modified", sa.String(1024)),
        sa.Column("id", sa.Uuid(), primary_key=True),
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
    )
    op.create_table(
        "source_run",
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error", sa.String(1000)),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
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
    )


def downgrade() -> None:
    op.drop_table("source_run")
    op.drop_table("source_snapshot")
    for name in (
        "consecutive_failures",
        "last_error",
        "last_modified",
        "etag",
        "status",
        "poll_interval_seconds",
        "adapter_type",
    ):
        op.drop_column("source", name)
