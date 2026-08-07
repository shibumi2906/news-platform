"""AI Core persistence: configuration, results, telemetry and provenance."""

from __future__ import annotations

import uuid
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class PromptTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "prompt_template"

    operation: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(String(1000), default=None)


class PromptVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "prompt_version"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_prompt_template_version"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_template.id"))
    version: Mapped[int] = mapped_column(Integer)
    system_prompt: Mapped[str] = mapped_column()
    user_prompt: Mapped[str] = mapped_column()
    output_schema: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class Topic(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Administrator-owned relevance configuration; no taxonomy is compiled into code."""

    __tablename__ = "topic"

    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    categories: Mapped[list[dict[str, Any]]] = mapped_column(PortableJSON, default=list)
    keywords: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    exclusions: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    regions: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    relevance_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    additional_rules: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AIOperationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_operation_run"

    operation: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_version.id"))
    status: Mapped[str] = mapped_column(String(32))
    input_hash: Mapped[str] = mapped_column(String(64))
    output: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, default=None)
    error_code: Mapped[str | None] = mapped_column(String(128), default=None)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class MaterialRelevance(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "material_relevance"
    __table_args__ = (
        UniqueConstraint("source_material_id", "topic_id", name="uq_material_relevance_topic"),
    )

    source_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_material.id"))
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topic.id"))
    category_slug: Mapped[str | None] = mapped_column(String(255), default=None)
    is_relevant: Mapped[bool] = mapped_column(Boolean)
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
    ai_operation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_operation_run.id"))


class ExtractedFact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "extracted_fact"

    source_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_material.id"))
    statement: Mapped[str] = mapped_column()
    fact_type: Mapped[str] = mapped_column(String(64))
    value: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float)
    ai_operation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_operation_run.id"))


class ExtractedEntity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "extracted_entity"

    source_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_material.id"))
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(512))
    normalized_name: Mapped[str] = mapped_column(String(512))
    confidence: Mapped[float] = mapped_column(Float)
    ai_operation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_operation_run.id"))


class DraftProvenance(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "draft_provenance"
    __table_args__ = (
        UniqueConstraint(
            "package_row_id", "source_material_id", "extracted_fact_id",
            name="uq_draft_provenance_source_fact",
        ),
    )

    package_row_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("canonical_news_package.id"))
    source_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_material.id"))
    extracted_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extracted_fact.id"), default=None
    )
