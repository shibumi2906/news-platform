"""Source and source material (docs/04_DATA_MODEL.md §3, docs/05 §2).

A `Source` is a configured RSS feed. `SourceMaterial` is raw connector
output persisted before any normalization — one row per `SourceCandidate`.
"""
# ruff: noqa: E501

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class Source(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "source"

    name: Mapped[str] = mapped_column(String(255))
    feed_url: Mapped[str] = mapped_column(String(2048))
    adapter_type: Mapped[str] = mapped_column(String(32), default="rss")
    config: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    status: Mapped[str] = mapped_column(String(32), default="active")
    is_active: Mapped[bool] = mapped_column(default=True)
    etag: Mapped[str | None] = mapped_column(String(1024), default=None)
    last_modified: Mapped[str | None] = mapped_column(String(1024), default=None)
    last_error: Mapped[str | None] = mapped_column(String(1000), default=None)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    health_status: Mapped[str] = mapped_column(String(32), default="healthy")
    health_reason: Mapped[str | None] = mapped_column(String(1000), default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class SourceSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "source_snapshot"
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"))
    status: Mapped[str] = mapped_column(String(32))
    body: Mapped[str | None] = mapped_column(default=None)
    content_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    etag: Mapped[str | None] = mapped_column(String(1024), default=None)
    last_modified: Mapped[str | None] = mapped_column(String(1024), default=None)


class SourceRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "source_run"
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"))
    status: Mapped[str] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(String(1000), default=None)
    created_count: Mapped[int] = mapped_column(Integer, default=0)


class SourceStateAudit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "source_state_audit"
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"))
    previous_status: Mapped[str | None] = mapped_column(String(32), default=None)
    status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(1000), default=None)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SourceMaterial(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "source_material"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_material_source_external"),
        UniqueConstraint(
            "source_id", "canonical_url_hash", name="uq_source_material_source_url_hash"
        ),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"))
    external_id: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str] = mapped_column(String(2048))
    canonical_url_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(1024))
    excerpt: Mapped[str | None] = mapped_column(String(4096), default=None)
    body: Mapped[str | None] = mapped_column(default=None)
    author: Mapped[str | None] = mapped_column(String(255), default=None)
    language: Mapped[str] = mapped_column(String(16))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class ParserSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "parser_snapshot"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"))
    url: Mapped[str] = mapped_column(String(2048))
    kind: Mapped[str] = mapped_column(String(32), default="list")
    html: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))


class ParserVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "parser_version"
    __table_args__ = (UniqueConstraint("source_id", "version", name="uq_parser_version"),)

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"))
    version: Mapped[int] = mapped_column(Integer)
    adapter_type: Mapped[str] = mapped_column(String(32))
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parser_version.id"), nullable=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parser_snapshot.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000), default=None)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reviewed_by_actor_id: Mapped[str | None] = mapped_column(String(255), default=None)


class ParserRepair(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "parser_repair"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"))
    detected_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parser_version.id"), nullable=True)
    proposed_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parser_version.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="detected")
    reason: Mapped[str] = mapped_column(String(1000))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
