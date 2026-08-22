"""Site article (docs/04_DATA_MODEL.md §4, ADR-004).

`SiteArticle` is independent of the incoming package once created — an
editor's changes are never silently overwritten by a new package version
(docs/10_EDITORIAL_WORKFLOW.md §2). `lock_version` is an optimistic
concurrency counter incremented on every mutating write; callers must pass
the version they last read or the write is rejected as a conflict.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from site_domain.workflow import ARTICLE_STATUSES, RECEIVED


class SiteArticle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "site_article"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in sorted(ARTICLE_STATUSES)) + ")",
            name="ck_site_article_status",
        ),
    )

    status: Mapped[str] = mapped_column(String(32), default=RECEIVED)
    #: Optimistic concurrency counter, incremented on every mutating write.
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    #: Highest `article_version.version_number` created for this article so far.
    latest_version_number: Mapped[int] = mapped_column(Integer, default=0)
    #: `True` requires a reviewer distinct from the version's author before approval.
    four_eyes_required: Mapped[bool] = mapped_column(default=True)
