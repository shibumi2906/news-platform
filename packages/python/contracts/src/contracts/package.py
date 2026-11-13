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

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.1"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0", "1.1"})

PackageOperation = Literal["created", "updated", "corrected", "retracted", "deleted"]


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
    source_name: str | None = None
    adapter_type: str | None = None
    author: str | None = None
    canonical_url: str | None = None
    content_hash: str | None = None


class PackageMedia(BaseModel):
    type: Literal["image", "video"]
    source_url: str
    thumbnail_url: str | None = None
    mime_type: str | None = None
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration: float | None = Field(default=None, ge=0)
    external_id: str | None = None
    provider: str | None = None
    source_material_id: UUID
    rights_hint: str = "link_only"
    attribution: str | None = None


class PackageGeography(BaseModel):
    country: str | None = None
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    state_or_region: str | None = None
    state_or_region_code: str | None = None
    metro: str | None = None
    city: str | None = None
    district: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: Literal["ai", "configured"]
    source_material_id: UUID | None = None

    @model_validator(mode="after")
    def require_location(self) -> PackageGeography:
        if not any(
            (
                self.country,
                self.country_code,
                self.state_or_region,
                self.state_or_region_code,
                self.metro,
                self.city,
                self.district,
            )
        ):
            raise ValueError("geography requires at least one location field")
        return self


class PackageTopic(BaseModel):
    id: UUID
    slug: str
    label: str | None = None


class PackageCategory(BaseModel):
    slug: str
    topic_id: UUID
    label: str | None = None
    parent_slug: str | None = None


class PackageAIProvenance(BaseModel):
    operation_run_id: UUID
    operation: str
    provider: str
    model: str
    prompt_version_id: UUID
    release_id: UUID | None = None


class PackageConfidence(BaseModel):
    overall: float = 1.0


class CanonicalNewsPackageEnvelope(BaseModel):
    schema_version: str = SCHEMA_VERSION
    package_id: UUID
    package_version: int
    instance_id: UUID
    event_id: UUID
    event_stage: str = "reported"
    operation: PackageOperation = "created"
    revision_reason: str | None = None
    content: PackageContent
    facts: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    taxonomy: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    topics: list[PackageTopic] = Field(default_factory=list)
    categories: list[PackageCategory] = Field(default_factory=list)
    geographies: list[PackageGeography] = Field(default_factory=list)
    sources: list[PackageSourceRef]
    language_versions: dict[str, PackageContent] = Field(default_factory=dict)
    media: list[PackageMedia] = Field(default_factory=list)
    ai_provenance: list[PackageAIProvenance] = Field(default_factory=list)
    rights: dict[str, Any] = Field(default_factory=lambda: {"usage": "link_only"})
    confidence: PackageConfidence = Field(default_factory=PackageConfidence)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
