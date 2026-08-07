from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RelevanceMatch(BaseModel):
    topic_id: UUID
    category_slug: str | None = None
    score: float = Field(ge=0, le=1)
    is_relevant: bool
    reason: dict[str, Any]


class RelevanceOutput(BaseModel):
    matches: list[RelevanceMatch]


class FactOutput(BaseModel):
    statement: str
    fact_type: str
    value: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)


class EntityOutput(BaseModel):
    kind: Literal["person", "organization", "place", "date", "other"]
    name: str
    confidence: float = Field(ge=0, le=1)


class ExtractionOutput(BaseModel):
    facts: list[FactOutput]
    entities: list[EntityOutput]
    dates: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    event_key: str = Field(min_length=1, max_length=512)


class DraftOutput(BaseModel):
    title: str
    lead: str
    body: str
    summary: str
    tags: list[str] = Field(default_factory=list)


class LanguageDetectionOutput(BaseModel):
    language_code: str = Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    confidence: float = Field(ge=0, le=1)


class TranslationOutput(BaseModel):
    title: str
    lead: str
    body: str
    summary: str
    tags: list[str]
