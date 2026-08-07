"""add AI core

Revision ID: 6a91bde40c22
Revises: 2f84c7a3d912
"""

# mypy: ignore-errors
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6a91bde40c22"
down_revision: str | None = "2f84c7a3d912"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _identity_columns() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.add_column("event", sa.Column("cluster_key", sa.String(512)))
    op.add_column("event", sa.Column("title", sa.String(1024)))
    op.add_column("event", sa.Column("summary", sa.String()))
    op.add_column(
        "event", sa.Column("cluster_confidence", sa.Float(), server_default="1", nullable=False)
    )
    op.create_unique_constraint("uq_event_cluster_key", "event", ["cluster_key"])

    op.create_table(
        "prompt_template",
        sa.Column("operation", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.String(1000)),
        *_identity_columns(),
    )
    op.create_table(
        "prompt_version",
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("prompt_template.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.String(), nullable=False),
        sa.Column("user_prompt", sa.String(), nullable=False),
        sa.Column("output_schema", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_identity_columns(),
        sa.UniqueConstraint("template_id", "version", name="uq_prompt_template_version"),
    )
    op.create_table(
        "topic",
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.String(2000)),
        sa.Column("categories", JSON, nullable=False),
        sa.Column("keywords", JSON, nullable=False),
        sa.Column("exclusions", JSON, nullable=False),
        sa.Column("regions", JSON, nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("relevance_threshold", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("additional_rules", JSON, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_identity_columns(),
    )
    op.create_table(
        "ai_operation_run",
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column(
            "prompt_version_id", sa.Uuid(), sa.ForeignKey("prompt_version.id"), nullable=False
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output", JSON),
        sa.Column("error_code", sa.String(128)),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), server_default="0", nullable=False),
        *_identity_columns(),
    )
    op.create_table(
        "material_relevance",
        sa.Column(
            "source_material_id", sa.Uuid(), sa.ForeignKey("source_material.id"), nullable=False
        ),
        sa.Column("topic_id", sa.Uuid(), sa.ForeignKey("topic.id"), nullable=False),
        sa.Column("category_slug", sa.String(255)),
        sa.Column("is_relevant", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reason", JSON, nullable=False),
        sa.Column(
            "ai_operation_run_id", sa.Uuid(), sa.ForeignKey("ai_operation_run.id"), nullable=False
        ),
        *_identity_columns(),
        sa.UniqueConstraint("source_material_id", "topic_id", name="uq_material_relevance_topic"),
    )
    op.create_table(
        "extracted_fact",
        sa.Column(
            "source_material_id", sa.Uuid(), sa.ForeignKey("source_material.id"), nullable=False
        ),
        sa.Column("statement", sa.String(), nullable=False),
        sa.Column("fact_type", sa.String(64), nullable=False),
        sa.Column("value", JSON, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "ai_operation_run_id", sa.Uuid(), sa.ForeignKey("ai_operation_run.id"), nullable=False
        ),
        *_identity_columns(),
    )
    op.create_table(
        "extracted_entity",
        sa.Column(
            "source_material_id", sa.Uuid(), sa.ForeignKey("source_material.id"), nullable=False
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("normalized_name", sa.String(512), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "ai_operation_run_id", sa.Uuid(), sa.ForeignKey("ai_operation_run.id"), nullable=False
        ),
        *_identity_columns(),
    )
    op.create_table(
        "event_material",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column(
            "source_material_id", sa.Uuid(), sa.ForeignKey("source_material.id"), nullable=False
        ),
        sa.Column("similarity_score", sa.Float(), server_default="1", nullable=False),
        *_identity_columns(),
        sa.UniqueConstraint("event_id", "source_material_id", name="uq_event_material"),
    )
    op.create_table(
        "draft_provenance",
        sa.Column(
            "package_row_id", sa.Uuid(), sa.ForeignKey("canonical_news_package.id"), nullable=False
        ),
        sa.Column(
            "source_material_id", sa.Uuid(), sa.ForeignKey("source_material.id"), nullable=False
        ),
        sa.Column("extracted_fact_id", sa.Uuid(), sa.ForeignKey("extracted_fact.id")),
        *_identity_columns(),
        sa.UniqueConstraint(
            "package_row_id",
            "source_material_id",
            "extracted_fact_id",
            name="uq_draft_provenance_source_fact",
        ),
    )


def downgrade() -> None:
    for table in (
        "draft_provenance",
        "event_material",
        "extracted_entity",
        "extracted_fact",
        "material_relevance",
        "ai_operation_run",
        "topic",
        "prompt_version",
        "prompt_template",
    ):
        op.drop_table(table)
    op.drop_constraint("uq_event_cluster_key", "event", type_="unique")
    for column in ("cluster_confidence", "summary", "title", "cluster_key"):
        op.drop_column("event", column)
