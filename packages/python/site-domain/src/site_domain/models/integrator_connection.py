"""Integrator connection (docs/04_DATA_MODEL.md §4, docs/21).

The site side's record of an upstream Integrator instance allowed to
deliver packages here. The HMAC secret is used to verify inbound
signatures.
"""

from __future__ import annotations

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class IntegratorConnection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "integrator_connection"

    name: Mapped[str] = mapped_column(String(255))
    hmac_secret: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
