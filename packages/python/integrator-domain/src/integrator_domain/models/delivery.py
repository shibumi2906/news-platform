"""Delivery and delivery attempt (docs/04_DATA_MODEL.md §4, docs/14 §5).

`Delivery` is idempotent per `(connection_id, idempotency_key)`.
`DeliveryAttempt` records each HTTP call the delivery-worker makes while
retrying a delivery.
"""

from __future__ import annotations

import uuid
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class Delivery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "delivery"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "idempotency_key", name="uq_delivery_connection_idempotency"
        ),
    )

    package_id: Mapped[uuid.UUID]
    package_version: Mapped[int] = mapped_column(Integer)
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_connection.id"))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending")


class DeliveryAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "delivery_attempt"

    delivery_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("delivery.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    response_status_code: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, default=None)
