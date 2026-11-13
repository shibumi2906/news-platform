"""Site connection (docs/04_DATA_MODEL.md §3, docs/21).

A registered downstream Site instance that packages are delivered to. The
HMAC secret is stored here and never leaves the integrator instance.
"""

from __future__ import annotations

from datetime import datetime

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class SiteConnection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "site_connection"

    name: Mapped[str] = mapped_column(String(255))
    delivery_url: Mapped[str] = mapped_column(String(2048))
    hmac_secret: Mapped[str] = mapped_column(String(255))
    active_key_id: Mapped[str] = mapped_column(String(64), default="legacy")
    previous_key_id: Mapped[str | None] = mapped_column(String(64), default=None)
    previous_hmac_secret: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(default=True)
    delivery_mode: Mapped[str] = mapped_column(String(16), default="push", server_default="push")
    last_pull_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    etag: Mapped[str | None] = mapped_column(String(1024), default=None)
    last_modified: Mapped[str | None] = mapped_column(String(1024), default=None)
