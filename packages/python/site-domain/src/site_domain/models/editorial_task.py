"""Editorial task queue entry (docs/10_EDITORIAL_WORKFLOW.md §1, docs/16_ADMIN_PANEL.md §1).

Tracks who still needs to look at an article and why. Not itself a status
transition — the article's `status` is the source of truth for workflow
state; a task is a work-queue pointer into it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin

OPEN = "open"
DONE = "done"
CANCELLED = "cancelled"

TASK_STATUSES = frozenset({OPEN, DONE, CANCELLED})


class EditorialTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "editorial_task"

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_article.id"))
    status: Mapped[str] = mapped_column(String(32), default=OPEN)
    #: Temporary actor identity (`X-Actor-Id`) until real auth/RBAC exists.
    assigned_actor_id: Mapped[str | None] = mapped_column(String(255), default=None)
    reason: Mapped[str | None] = mapped_column(String(1000), default=None)
