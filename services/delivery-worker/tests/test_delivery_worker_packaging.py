from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from delivery_worker.packaging import package_row_to_envelope
from integrator_domain.models import CanonicalNewsPackage


def test_package_row_to_envelope_round_trips_a_persisted_row() -> None:
    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    event_id = uuid4()
    source_id = uuid4()
    material_id = uuid4()
    package = CanonicalNewsPackage(
        package_id=uuid4(),
        package_version=1,
        instance_id=uuid4(),
        event_id=event_id,
        event_stage="reported",
        content={
            "title": "Headline",
            "excerpt": "Summary",
            "body": "Body",
            "canonical_url": "https://news.example.com/a",
            "language": "en",
        },
        facts=[],
        entities=[],
        taxonomy=[],
        sources=[
            {
                "source_id": str(source_id),
                "source_material_id": str(material_id),
                "external_id": "ext-1",
                "url": "https://news.example.com/a?utm=1",
                "published_at": now.isoformat(),
                "fetched_at": now.isoformat(),
            }
        ],
        language_versions={},
        media=[],
        rights={"usage": "link_only"},
        confidence={"overall": 1.0},
        warnings=[],
        created_at=now,
        updated_at=now,
    )

    envelope = package_row_to_envelope(package)

    assert envelope.package_id == package.package_id
    assert envelope.event_id == event_id
    assert envelope.content.title == "Headline"
    assert envelope.content.canonical_url == "https://news.example.com/a"
    assert len(envelope.sources) == 1
    assert envelope.sources[0].source_id == source_id
    assert envelope.sources[0].source_material_id == material_id
    assert envelope.confidence.overall == 1.0

    body = envelope.model_dump_json()
    assert '"package_id"' in body
