"""Builds a `CanonicalNewsPackage` directly from a `SourceMaterial` + `Event`.

Stage 1B scope reduction (explicitly approved, see `contracts.package`): no
AI normalization step exists yet, so `content` is copied straight from the
RSS-derived `SourceMaterial` and `facts`/`entities`/`taxonomy`/`media` are
empty.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from common.ids import new_uuid
from common.time import utc_now
from contracts.package import (
    CanonicalNewsPackageEnvelope,
    PackageAIProvenance,
    PackageCategory,
    PackageConfidence,
    PackageContent,
    PackageGeography,
    PackageMedia,
    PackageSourceRef,
    PackageTopic,
)
from integrator_domain.models import CanonicalNewsPackage, Event, SourceMaterial

from processing_worker.schemas import DraftOutput


def build_package_envelope(
    material: SourceMaterial, event: Event, *, instance_id: UUID
) -> CanonicalNewsPackageEnvelope:
    now = utc_now()
    return CanonicalNewsPackageEnvelope(
        package_id=new_uuid(),
        package_version=1,
        instance_id=instance_id,
        event_id=event.id,
        event_stage=event.stage,
        operation="created",
        content=PackageContent(
            title=material.title,
            excerpt=material.excerpt,
            body=material.body,
            canonical_url=material.canonical_url,
            language=material.language,
        ),
        sources=[
            PackageSourceRef(
                source_id=material.source_id,
                source_material_id=material.id,
                external_id=material.external_id,
                url=material.url,
                published_at=material.published_at,
                fetched_at=material.fetched_at,
            )
        ],
        created_at=now,
        updated_at=now,
    )


def build_ai_package_envelope(
    materials: list[SourceMaterial],
    event: Event,
    draft: DraftOutput,
    *,
    instance_id: UUID,
    package_id: UUID,
    package_version: int,
    facts: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    taxonomy: list[str],
    regions: list[str],
    topics: list[PackageTopic],
    categories: list[PackageCategory],
    geographies: list[PackageGeography],
    media: list[PackageMedia],
    ai_provenance: list[PackageAIProvenance],
    source_refs: list[PackageSourceRef],
    source_language: str,
    source_direction: str,
    language_versions: dict[str, PackageContent],
) -> CanonicalNewsPackageEnvelope:
    if not materials:
        raise ValueError("an AI package requires at least one source material")
    now = utc_now()
    primary = materials[0]
    return CanonicalNewsPackageEnvelope(
        package_id=package_id,
        package_version=package_version,
        instance_id=instance_id,
        event_id=event.id,
        event_stage=event.stage,
        operation="created" if package_version == 1 else "updated",
        content=PackageContent(
            title=draft.title,
            lead=draft.lead,
            excerpt=draft.summary,
            body=draft.body,
            summary=draft.summary,
            tags=draft.tags,
            canonical_url=primary.canonical_url,
            language=source_language,
            direction="rtl" if source_direction == "rtl" else "ltr",
        ),
        facts=facts,
        entities=entities,
        taxonomy=taxonomy,
        regions=regions,
        topics=topics,
        categories=categories,
        geographies=geographies,
        language_versions=language_versions,
        sources=source_refs,
        media=media,
        ai_provenance=ai_provenance,
        confidence=PackageConfidence(
            overall=min([0.9, *[float(fact["confidence"]) for fact in facts]])
        ),
        created_at=now,
        updated_at=now,
    )


def envelope_to_row(envelope: CanonicalNewsPackageEnvelope) -> CanonicalNewsPackage:
    return CanonicalNewsPackage(
        package_id=envelope.package_id,
        package_version=envelope.package_version,
        instance_id=envelope.instance_id,
        event_id=envelope.event_id,
        event_stage=envelope.event_stage,
        operation=envelope.operation,
        revision_reason=envelope.revision_reason,
        content=envelope.content.model_dump(mode="json"),
        facts=envelope.facts,
        entities=envelope.entities,
        taxonomy=envelope.taxonomy,
        regions=envelope.regions,
        topics=[item.model_dump(mode="json") for item in envelope.topics],
        categories=[item.model_dump(mode="json") for item in envelope.categories],
        geographies=[item.model_dump(mode="json") for item in envelope.geographies],
        sources=[source.model_dump(mode="json") for source in envelope.sources],
        language_versions={
            language: content.model_dump(mode="json")
            for language, content in envelope.language_versions.items()
        },
        media=[item.model_dump(mode="json") for item in envelope.media],
        ai_provenance=[item.model_dump(mode="json") for item in envelope.ai_provenance],
        rights=envelope.rights,
        confidence=envelope.confidence.model_dump(mode="json"),
        warnings=envelope.warnings,
    )
