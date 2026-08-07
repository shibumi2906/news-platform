"""Ingestion attempt (docs/14_PUBLIC_AND_INTERNAL_API.md §5).

Records each ingestion request per `(connection_id, idempotency_key)` so a
retried request with the same key returns the stored result, and the same
key with a different body is rejected as a conflict.
"""

from __future__ import annotations

import uuid
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class IngestionAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_attempt"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "idempotency_key", name="uq_ingestion_attempt_connection_idempotency"
        ),
        UniqueConstraint("connection_id", "nonce", name="uq_ingestion_attempt_connection_nonce"),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrator_connection.id"))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    nonce: Mapped[str] = mapped_column(String(255), default="")
    request_body_hash: Mapped[str] = mapped_column(String(64))
    package_id: Mapped[uuid.UUID]
    package_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    response_body: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
