"""Review decision (docs/10_EDITORIAL_WORKFLOW.md §3).

Records who approved or rejected a specific article version. Four-eyes
enforcement (`reviewer_actor_id != ArticleVersion.created_by_actor_id`) is
checked by the service layer before a row is inserted here, not by a
database constraint, since it depends on a per-article `four_eyes_required`
flag.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin

APPROVED = "approved"
REJECTED = "rejected"

REVIEW_DECISIONS = frozenset({APPROVED, REJECTED})


class ReviewDecision(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "review_decision"

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_article.id"))
    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_version.id"))
    #: Temporary actor identity (`X-Actor-Id`) until real auth/RBAC exists.
    reviewer_actor_id: Mapped[str] = mapped_column(String(255))
    decision: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(1000), default=None)
