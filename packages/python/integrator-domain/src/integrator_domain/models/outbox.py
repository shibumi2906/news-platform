"""Concrete transactional outbox table (ADR-006).

Implements `common.outbox.OutboxWriter`: a row is written in the same DB
transaction as the domain state change it announces. A fast-path dispatch
happens right after commit; a periodic relay re-scans rows still `pending`
as a durability safety net if the process crashes before dispatching.
"""

from __future__ import annotations

from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class OutboxEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "outbox_event"

    event_type: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
    status: Mapped[str] = mapped_column(String(32), default="pending")
