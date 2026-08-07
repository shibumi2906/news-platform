"""add multilingual layer

Revision ID: 8c4e7a19d5b0
Revises: 6a91bde40c22
"""

# mypy: ignore-errors
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8c4e7a19d5b0"
down_revision: str | None = "6a91bde40c22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _identity_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    language = op.create_table(
        "language_config",
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("direction", sa.String(3), server_default="ltr", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("translation_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_identity_columns(),
        sa.CheckConstraint("direction IN ('ltr', 'rtl')"),
    )
    rows = [
        ("en", "English", "ltr"),
        ("de", "German", "ltr"),
        ("fr", "French", "ltr"),
        ("es", "Spanish", "ltr"),
        ("pt-BR", "Portuguese (Brazil)", "ltr"),
        ("id", "Indonesian", "ltr"),
        ("ar", "Arabic", "rtl"),
        ("zh-CN", "Chinese (Simplified)", "ltr"),
        ("ja", "Japanese", "ltr"),
        ("th", "Thai", "ltr"),
        ("vi", "Vietnamese", "ltr"),
        ("ko", "Korean", "ltr"),
        ("it", "Italian", "ltr"),
        ("sw", "Swahili", "ltr"),
        ("ha", "Hausa", "ltr"),
        ("am", "Amharic", "ltr"),
    ]
    op.bulk_insert(
        language,
        [
            {
                "id": uuid.uuid5(uuid.NAMESPACE_URL, f"news-platform-language:{code}"),
                "code": code,
                "name": name,
                "direction": direction,
                "priority": 16 - index,
                "is_active": True,
                "translation_enabled": False,
            }
            for index, (code, name, direction) in enumerate(rows)
        ],
    )
    op.create_table(
        "terminology_entry",
        sa.Column(
            "source_language_code",
            sa.String(16),
            sa.ForeignKey("language_config.code"),
            nullable=False,
        ),
        sa.Column(
            "target_language_code",
            sa.String(16),
            sa.ForeignKey("language_config.code"),
            nullable=False,
        ),
        sa.Column("source_term", sa.String(512), nullable=False),
        sa.Column("target_term", sa.String(512), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_identity_columns(),
        sa.UniqueConstraint(
            "source_language_code",
            "target_language_code",
            "source_term",
            name="uq_terminology_language_term",
        ),
    )
    op.create_table(
        "material_language_detection",
        sa.Column(
            "source_material_id",
            sa.Uuid(),
            sa.ForeignKey("source_material.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "language_code", sa.String(16), sa.ForeignKey("language_config.code"), nullable=False
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "ai_operation_run_id", sa.Uuid(), sa.ForeignKey("ai_operation_run.id"), nullable=False
        ),
        *_identity_columns(),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1"),
    )
    op.create_table(
        "translation_version",
        sa.Column(
            "package_row_id", sa.Uuid(), sa.ForeignKey("canonical_news_package.id"), nullable=False
        ),
        sa.Column(
            "source_language_code",
            sa.String(16),
            sa.ForeignKey("language_config.code"),
            nullable=False,
        ),
        sa.Column(
            "target_language_code",
            sa.String(16),
            sa.ForeignKey("language_config.code"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("content", JSON, nullable=False),
        sa.Column("terminology_revision", sa.String(64), nullable=False),
        sa.Column(
            "ai_operation_run_id", sa.Uuid(), sa.ForeignKey("ai_operation_run.id"), nullable=False
        ),
        *_identity_columns(),
        sa.UniqueConstraint("package_row_id", "target_language_code", name="uq_translation_target"),
        sa.CheckConstraint("direction IN ('ltr', 'rtl')"),
    )


def downgrade() -> None:
    op.drop_table("translation_version")
    op.drop_table("material_language_detection")
    op.drop_table("terminology_entry")
    op.drop_table("language_config")
