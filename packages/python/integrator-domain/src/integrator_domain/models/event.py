"""Event (docs/04_DATA_MODEL.md §3, docs/08).

Stage 1B scope reduction, explicitly approved: an `Event` is created 1:1
per `SourceMaterial`, as a temporary stub. Multi-source event clustering is
out of scope until AI processing is introduced.
"""

from __future__ import annotations

import uuid

from common.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class Event(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event"
    __table_args__ = (UniqueConstraint("source_material_id", name="uq_event_source_material"),)

    source_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_material.id"))
    stage: Mapped[str] = mapped_column(String(32), default="reported")
    cluster_key: Mapped[str | None] = mapped_column(String(512), unique=True, default=None)
    title: Mapped[str | None] = mapped_column(String(1024), default=None)
    summary: Mapped[str | None] = mapped_column(default=None)
    cluster_confidence: Mapped[float] = mapped_column(Float, default=1.0)


class EventMaterial(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event_material"
    __table_args__ = (
        UniqueConstraint("event_id", "source_material_id", name="uq_event_material"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    source_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_material.id"))
    similarity_score: Mapped[float] = mapped_column(Float, default=1.0)
