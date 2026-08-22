"""Correction notice (docs/10_EDITORIAL_WORKFLOW.md §4: a correction carries
a visible explanation per policy)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CorrectionNotice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "correction_notice"

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_article.id"))
    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_version.id"))
    explanation: Mapped[str] = mapped_column(String(2000))
