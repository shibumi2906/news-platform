"""Configurable language catalog, terminology and immutable translations."""

from __future__ import annotations

import uuid
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class LanguageConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "language_config"
    __table_args__ = (
        CheckConstraint("direction IN ('ltr', 'rtl')", name="language_config_direction_check"),
    )

    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    direction: Mapped[str] = mapped_column(String(3), default="ltr")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    translation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class TerminologyEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "terminology_entry"
    __table_args__ = (
        UniqueConstraint(
            "source_language_code",
            "target_language_code",
            "source_term",
            name="uq_terminology_language_term",
        ),
    )

    source_language_code: Mapped[str] = mapped_column(ForeignKey("language_config.code"))
    target_language_code: Mapped[str] = mapped_column(ForeignKey("language_config.code"))
    source_term: Mapped[str] = mapped_column(String(512))
    target_term: Mapped[str] = mapped_column(String(512))
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MaterialLanguageDetection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "material_language_detection"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="material_language_detection_confidence_check",
        ),
    )

    source_material_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_material.id"), unique=True
    )
    language_code: Mapped[str] = mapped_column(ForeignKey("language_config.code"))
    confidence: Mapped[float] = mapped_column(Float)
    ai_operation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_operation_run.id"))


class TranslationVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "translation_version"
    __table_args__ = (
        UniqueConstraint("package_row_id", "target_language_code", name="uq_translation_target"),
        CheckConstraint("direction IN ('ltr', 'rtl')", name="translation_version_direction_check"),
    )

    package_row_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("canonical_news_package.id"))
    source_language_code: Mapped[str] = mapped_column(ForeignKey("language_config.code"))
    target_language_code: Mapped[str] = mapped_column(ForeignKey("language_config.code"))
    direction: Mapped[str] = mapped_column(String(3))
    content: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
    terminology_revision: Mapped[str] = mapped_column(String(64))
    ai_operation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_operation_run.id"))
