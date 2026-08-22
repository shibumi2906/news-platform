"""Builds a `CanonicalNewsPackage` directly from a `SourceMaterial` + `Event`.

Stage 1B scope reduction (explicitly approved, see `contracts.package`): no
AI normalization step exists yet, so `content` is copied straight from the
RSS-derived `SourceMaterial` and `facts`/`entities`/`taxonomy`/`media` are
empty.
"""

from __future__ import annotations

from uuid import UUID

from common.ids import new_uuid
from common.time import utc_now
from contracts.package import CanonicalNewsPackageEnvelope, PackageContent, PackageSourceRef
from integrator_domain.models import CanonicalNewsPackage, Event, SourceMaterial


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


def envelope_to_row(envelope: CanonicalNewsPackageEnvelope) -> CanonicalNewsPackage:
    return CanonicalNewsPackage(
        package_id=envelope.package_id,
        package_version=envelope.package_version,
        instance_id=envelope.instance_id,
        event_id=envelope.event_id,
        event_stage=envelope.event_stage,
        content=envelope.content.model_dump(mode="json"),
        facts=envelope.facts,
        entities=envelope.entities,
        taxonomy=envelope.taxonomy,
        sources=[source.model_dump(mode="json") for source in envelope.sources],
        language_versions={
            language: content.model_dump(mode="json")
            for language, content in envelope.language_versions.items()
        },
        media=envelope.media,
        rights=envelope.rights,
        confidence=envelope.confidence.model_dump(mode="json"),
        warnings=envelope.warnings,
    )
