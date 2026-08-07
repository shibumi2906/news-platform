"""Canonical news package envelope.

docs/14_PUBLIC_AND_INTERNAL_API.md §4 defines the required envelope fields.
Stage 1B builds `content` directly from RSS `SourceCandidate` data with no AI
step, and every `event` is a temporary 1:1 stub over a single source
material — both are explicitly approved scope reductions, not omissions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class PackageContent(BaseModel):
    title: str
    lead: str | None = None
    excerpt: str | None = None
    body: str | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    canonical_url: str
    language: str
    direction: Literal["ltr", "rtl"] = "ltr"


class PackageSourceRef(BaseModel):
    source_id: UUID
    source_material_id: UUID
    external_id: str
    url: str
    published_at: datetime
    fetched_at: datetime


class PackageConfidence(BaseModel):
    overall: float = 1.0


class CanonicalNewsPackageEnvelope(BaseModel):
    schema_version: str = SCHEMA_VERSION
    package_id: UUID
    package_version: int
    instance_id: UUID
    event_id: UUID
    event_stage: str = "reported"
    content: PackageContent
    facts: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    taxonomy: list[str] = Field(default_factory=list)
    sources: list[PackageSourceRef]
    language_versions: dict[str, PackageContent] = Field(default_factory=dict)
    media: list[dict[str, Any]] = Field(default_factory=list)
    rights: dict[str, Any] = Field(default_factory=lambda: {"usage": "link_only"})
    confidence: PackageConfidence = Field(default_factory=PackageConfidence)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
