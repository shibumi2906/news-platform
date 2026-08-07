"""Media metadata, rights, generation, memes, and video foundations."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class MediaAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "media_asset"
    __table_args__ = (
        UniqueConstraint("bucket", "object_key", name="uq_media_asset_object"),
        CheckConstraint(
            "status IN ('pending', 'ready', 'rejected', 'failed', 'deleted')",
            name="media_asset_status_check",
        ),
    )

    bucket: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(1024))
    storage_provider: Mapped[str] = mapped_column(String(32), default="s3")
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    mime_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer, default=None)
    height: Mapped[int | None] = mapped_column(Integer, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    parent_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_asset.id"), default=None
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    source_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    provenance: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    rights: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)


class ArticleMediaLink(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "article_media_link"
    __table_args__ = (
        UniqueConstraint(
            "media_asset_id",
            "article_version_id",
            "translation_version_id",
            "role",
            name="uq_article_media_link",
            postgresql_nulls_not_distinct=True,
        ),
    )

    media_asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_asset.id"))
    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_version.id"))
    translation_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("article_translation_version.id"), default=None
    )
    role: Mapped[str] = mapped_column(String(32), default="hero")
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class MediaGenerationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "media_generation_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'moderated', 'failed')",
            name="media_generation_run_status_check",
        ),
    )

    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_version.id"))
    operation: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    prompt_version: Mapped[str] = mapped_column(String(32), default="1")
    prompt_hash: Mapped[str] = mapped_column(String(64))
    variant_count: Mapped[int] = mapped_column(Integer, default=1)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    moderation: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)


class MemeTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "meme_template"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    base_asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_asset.id"))
    layout: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MemeVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "meme_version"
    __table_args__ = (
        UniqueConstraint("template_id", "version_number", name="uq_meme_template_version"),
        CheckConstraint("mode IN ('manual', 'ai')", name="meme_version_mode_check"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meme_template.id"))
    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_version.id"))
    output_asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_asset.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))
    caption: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class VideoProject(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "video_project"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'ready', 'rendering', 'rendered', 'failed')",
            name="video_project_status_check",
        ),
    )

    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_version.id"))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    script: Mapped[str] = mapped_column(Text)
    storyboard: Mapped[list[dict[str, Any]]] = mapped_column(PortableJSON, default=list)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    telemetry: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
