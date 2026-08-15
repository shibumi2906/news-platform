"""Event clustering models (docs/04_DATA_MODEL.md §3, docs/08)."""

from __future__ import annotations

import uuid
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class Event(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event"
    # Kept only for compatibility with pre-intelligence source stubs.  Final
    # cluster membership is represented exclusively by EventMaterial.
    source_material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_material.id"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(32), default="reported")
    cluster_key: Mapped[str | None] = mapped_column(String(512), default=None)
    title: Mapped[str | None] = mapped_column(String(1024), default=None)
    summary: Mapped[str | None] = mapped_column(default=None)
    cluster_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default="active")
    merged_into_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event.id"), nullable=True
    )


class EventMaterial(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event_material"
    __table_args__ = (UniqueConstraint("event_id", "source_material_id", name="uq_event_material"),)

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    source_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_material.id"))
    similarity_score: Mapped[float] = mapped_column(Float, default=1.0)
    decision: Mapped[str] = mapped_column(String(32), default="separate")
    evidence: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class EventClusteringPolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event_clustering_policy"

    auto_merge_threshold: Mapped[float] = mapped_column(Float, default=0.88)
    review_threshold: Mapped[float] = mapped_column(Float, default=0.65)
    candidate_window_hours: Mapped[int] = mapped_column(default=168)


class EventMatchReview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event_match_review"
    __table_args__ = (
        UniqueConstraint(
            "source_material_id", "candidate_event_id", name="uq_event_review_candidate"
        ),
    )

    source_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_material.id"))
    proposed_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    candidate_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    score: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    resolved_by_actor_id: Mapped[str | None] = mapped_column(String(255), default=None)


class EventClusterOperation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event_cluster_operation"

    operation: Mapped[str] = mapped_column(String(32))
    target_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("event.id"), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(255), default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
