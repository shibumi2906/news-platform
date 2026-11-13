from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from contracts import (
    CanonicalNewsPackageEnvelope,
    IncomingPackageReceipt,
    PackageContent,
    PackageGeography,
    PackageMedia,
    PackageSourceRef,
    SourceCandidate,
)
from contracts.schema_export import SCHEMA_PATH, export_schema


def test_source_candidate_round_trips() -> None:
    candidate = SourceCandidate(
        source_id=uuid4(),
        external_id="12345",
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        title="Trailer released",
        language="en",
        published_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
    )
    restored = SourceCandidate.model_validate_json(candidate.model_dump_json())
    assert restored == candidate


def test_canonical_news_package_envelope_round_trips() -> None:
    now = datetime.now(UTC)
    source_id = uuid4()
    envelope = CanonicalNewsPackageEnvelope(
        package_id=uuid4(),
        package_version=1,
        instance_id=uuid4(),
        event_id=uuid4(),
        content=PackageContent(
            title="Trailer released",
            canonical_url="https://example.com/article",
            language="en",
        ),
        sources=[
            PackageSourceRef(
                source_id=source_id,
                source_material_id=uuid4(),
                external_id="12345",
                url="https://example.com/article",
                published_at=now,
                fetched_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )
    restored = CanonicalNewsPackageEnvelope.model_validate_json(envelope.model_dump_json())
    assert restored == envelope
    assert restored.schema_version == "1.1"
    assert restored.event_stage == "reported"
    assert restored.rights == {"usage": "link_only"}


def test_incoming_package_receipt_accepts_known_status() -> None:
    receipt = IncomingPackageReceipt(
        package_id=uuid4(),
        package_version=1,
        status="accepted",
        received_at=datetime.now(UTC),
    )
    assert receipt.status == "accepted"


def test_v1_0_payload_remains_compatible_with_additive_defaults() -> None:
    now = datetime.now(UTC)
    payload = {
        "schema_version": "1.0",
        "package_id": str(uuid4()),
        "package_version": 1,
        "instance_id": str(uuid4()),
        "event_id": str(uuid4()),
        "content": {
            "title": "Legacy",
            "canonical_url": "https://example.test/legacy",
            "language": "en",
        },
        "sources": [
            {
                "source_id": str(uuid4()),
                "source_material_id": str(uuid4()),
                "external_id": "legacy-1",
                "url": "https://example.test/legacy",
                "published_at": now.isoformat(),
                "fetched_at": now.isoformat(),
            }
        ],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    restored = CanonicalNewsPackageEnvelope.model_validate(payload)
    assert restored.operation == "created"
    assert restored.topics == []
    assert restored.geographies == []


def test_typed_media_and_multiple_geographies_round_trip() -> None:
    material_id = uuid4()
    media = PackageMedia(
        type="video",
        source_url="https://youtube.test/watch?v=one",
        thumbnail_url="https://img.test/one.jpg",
        width=1280,
        height=720,
        external_id="one",
        provider="youtube",
        source_material_id=material_id,
    )
    geographies = [
        PackageGeography(
            country="United States",
            country_code="US",
            state_or_region="Texas",
            state_or_region_code="TX",
            city="Dallas",
            confidence=0.91,
            source="ai",
            source_material_id=material_id,
        ),
        PackageGeography(country_code="GB", city="London", source="ai", confidence=0.8),
    ]
    assert PackageMedia.model_validate_json(media.model_dump_json()) == media
    assert [item.city for item in geographies] == ["Dallas", "London"]


def test_checked_in_json_schema_artifact_matches_current_model() -> None:
    checked_in = SCHEMA_PATH.read_text(encoding="utf-8")
    assert checked_in == export_schema() + "\n", (
        "packages/schemas/canonical_news_package.schema.json is stale — "
        "run `uv run python -m contracts.schema_export`"
    )
