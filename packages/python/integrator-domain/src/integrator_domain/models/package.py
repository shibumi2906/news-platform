"""Canonical news package (docs/04_DATA_MODEL.md §3, docs/14 §4).

A package is versioned and immutable once written: a new package version is
a new row, never an in-place update of `content`.
"""

from __future__ import annotations

import uuid
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CanonicalNewsPackage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "canonical_news_package"
    __table_args__ = (
        UniqueConstraint("package_id", "package_version", name="uq_package_id_version"),
    )

    package_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)
    package_version: Mapped[int] = mapped_column(Integer)
    instance_id: Mapped[uuid.UUID]
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    event_stage: Mapped[str] = mapped_column(String(32), default="reported")
    content: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
    facts: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    entities: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    taxonomy: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    sources: Mapped[list[Any]] = mapped_column(PortableJSON)
    language_versions: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    media: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    rights: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=lambda: {"usage": "link_only"}
    )
    confidence: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=lambda: {"overall": 1.0}
    )
    warnings: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
