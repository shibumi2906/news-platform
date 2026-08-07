"""Immutable translation linked to the exact source ArticleVersion."""

from __future__ import annotations

import uuid
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ArticleTranslationVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "article_translation_version"
    __table_args__ = (
        UniqueConstraint(
            "article_version_id", "language_code", name="uq_article_translation_language"
        ),
        CheckConstraint("direction IN ('ltr', 'rtl')"),
    )

    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_version.id"))
    source_language_code: Mapped[str] = mapped_column(String(16))
    language_code: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(3))
    content: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
