"""Source and source material (docs/04_DATA_MODEL.md §3, docs/05 §2).

A `Source` is a configured RSS feed. `SourceMaterial` is raw connector
output persisted before any normalization — one row per `SourceCandidate`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class Source(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "source"

    name: Mapped[str] = mapped_column(String(255))
    feed_url: Mapped[str] = mapped_column(String(2048))
    is_active: Mapped[bool] = mapped_column(default=True)


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
