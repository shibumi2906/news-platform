"""Rebuilds the wire envelope from a persisted `CanonicalNewsPackage` row.

Inverse of `processing_worker.packaging.envelope_to_row`: the delivery-worker
never mutates package content, only re-serializes it for signing and
transport.
"""

from __future__ import annotations

from contracts.package import (
    CanonicalNewsPackageEnvelope,
    PackageConfidence,
    PackageContent,
    PackageSourceRef,
)
from integrator_domain.models import CanonicalNewsPackage


def package_row_to_envelope(package: CanonicalNewsPackage) -> CanonicalNewsPackageEnvelope:
    return CanonicalNewsPackageEnvelope(
        package_id=package.package_id,
        package_version=package.package_version,
        instance_id=package.instance_id,
        event_id=package.event_id,
        event_stage=package.event_stage,
        content=PackageContent(**package.content),
        facts=package.facts,
        entities=package.entities,
        taxonomy=package.taxonomy,
        regions=package.regions or [],
        sources=[PackageSourceRef(**source) for source in package.sources],
        language_versions={
            language: PackageContent(**content)
            for language, content in package.language_versions.items()
        },
        media=package.media,
        rights=package.rights,
        confidence=PackageConfidence(**package.confidence),
        warnings=package.warnings,
        created_at=package.created_at,
        updated_at=package.updated_at,
    )
