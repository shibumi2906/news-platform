"""Site-local entities and their immutable article-version associations."""

from __future__ import annotations

import uuid

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class SiteEntity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "site_entity"
    __table_args__ = (
        UniqueConstraint("kind", "normalized_name", name="uq_site_entity_kind_normalized_name"),
    )

    name: Mapped[str] = mapped_column(String(1024))
    normalized_name: Mapped[str] = mapped_column(String(1024))
    kind: Mapped[str] = mapped_column(String(255))


class ArticleVersionEntity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "article_version_entity"
    __table_args__ = (
        UniqueConstraint(
            "article_version_id", "entity_id", name="uq_article_version_entity_association"
        ),
    )

    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_version.id"))
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_entity.id"))
