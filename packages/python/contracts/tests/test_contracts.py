from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from contracts import (
    CanonicalNewsPackageEnvelope,
    IncomingPackageReceipt,
    PackageContent,
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
    assert restored.schema_version == "1.0"
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


def test_checked_in_json_schema_artifact_matches_current_model() -> None:
    checked_in = SCHEMA_PATH.read_text(encoding="utf-8")
    assert checked_in == export_schema() + "\n", (
        "packages/schemas/canonical_news_package.schema.json is stale — "
        "run `uv run python -m contracts.schema_export`"
    )
