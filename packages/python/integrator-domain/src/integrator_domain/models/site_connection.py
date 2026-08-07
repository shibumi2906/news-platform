"""Site connection (docs/04_DATA_MODEL.md §3, docs/21).

A registered downstream Site instance that packages are delivered to. The
HMAC secret is stored here and never leaves the integrator instance.
"""

from __future__ import annotations

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class SiteConnection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "site_connection"

    name: Mapped[str] = mapped_column(String(255))
    delivery_url: Mapped[str] = mapped_column(String(2048))
    hmac_secret: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    etag: Mapped[str | None] = mapped_column(String(1024), default=None)
    last_modified: Mapped[str | None] = mapped_column(String(1024), default=None)
