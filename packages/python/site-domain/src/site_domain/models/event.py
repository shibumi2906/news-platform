"""Site-local projection of an Integrator event for public timelines."""

from __future__ import annotations

import uuid

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class SiteEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "site_event"

    source_event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    title: Mapped[str] = mapped_column(String(1024))
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    taxonomy: Mapped[list[str]] = mapped_column(JSON, default=list)
