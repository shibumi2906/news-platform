"""Publication (docs/04_DATA_MODEL.md §4, docs/10_EDITORIAL_WORKFLOW.md §4).

One `Publication` row per article. `active_article_version_id` is switched
atomically by the service layer alongside `status` and the publication
event write. Schedule/embargo timestamps are UTC.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEDULED = "scheduled"
PUBLISHING = "publishing"
PUBLISHED = "published"
UNPUBLISHED = "unpublished"

PUBLICATION_STATUSES = frozenset({SCHEDULED, PUBLISHING, PUBLISHED, UNPUBLISHED})


class Publication(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "publication"
    __table_args__ = (UniqueConstraint("article_id", name="uq_publication_article"),)

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_article.id"))
    active_article_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("article_version.id"), default=None
    )
    status: Mapped[str] = mapped_column(String(32))
    #: Embargo/schedule time; the article must not go live before this instant.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    unpublished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
