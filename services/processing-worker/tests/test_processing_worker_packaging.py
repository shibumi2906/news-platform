from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from integrator_domain.models import Event, Source, SourceMaterial
from processing_worker.packaging import build_package_envelope, envelope_to_row
from processing_worker.processing import _material_media, _source_ref


def _make_material_and_event() -> tuple[SourceMaterial, Event]:
    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    source_id = uuid4()
    material = SourceMaterial(
        id=uuid4(),
        source_id=source_id,
        external_id="ext-1",
        url="https://news.example.com/a?utm=1",
        canonical_url="https://news.example.com/a",
        canonical_url_hash="deadbeef",
        title="Headline",
        excerpt="Summary",
        body="Body",
        author="Reporter",
        language="en",
        published_at=now,
        fetched_at=now,
        raw={},
    )
    event = Event(id=uuid4(), source_material_id=material.id, stage="reported")
    return material, event


def test_build_package_envelope_copies_material_fields_verbatim() -> None:
    material, event = _make_material_and_event()
    instance_id = uuid4()

    envelope = build_package_envelope(material, event, instance_id=instance_id)

    assert envelope.package_version == 1
    assert envelope.instance_id == instance_id
    assert envelope.event_id == event.id
    assert envelope.event_stage == "reported"
    assert envelope.content.title == material.title
    assert envelope.content.canonical_url == material.canonical_url
    assert envelope.facts == []
    assert envelope.entities == []
    assert envelope.taxonomy == []
    assert len(envelope.sources) == 1
    assert envelope.sources[0].source_material_id == material.id
    assert envelope.sources[0].source_id == material.source_id


def test_envelope_to_row_produces_json_serializable_columns() -> None:
    material, event = _make_material_and_event()
    envelope = build_package_envelope(material, event, instance_id=uuid4())

    row = envelope_to_row(envelope)

    json.dumps(row.content)
    json.dumps(row.sources)
    json.dumps(row.rights)
    json.dumps(row.confidence)
    assert row.package_id == envelope.package_id
    assert row.event_id == event.id
    assert row.sources[0]["source_material_id"] == str(material.id)


def test_youtube_media_and_source_provenance_are_normalized_without_fabrication() -> None:
    material, _ = _make_material_and_event()
    material.url = "https://www.youtube.com/watch?v=video-one"
    material.external_id = "video-one"
    material.raw = {
        "adapter": "youtube",
        "thumbnails": {
            "small": {"url": "https://img.test/s.jpg", "width": 320, "height": 180},
            "large": {"url": "https://img.test/l.jpg", "width": 1280, "height": 720},
        },
    }
    source = Source(
        id=material.source_id,
        name="Video Wire",
        feed_url="https://youtube.test/channel",
        adapter_type="youtube",
    )
    media = _material_media(material)
    reference = _source_ref(material, source)
    assert len(media) == 1
    assert media[0].type == "video"
    assert media[0].thumbnail_url == "https://img.test/l.jpg"
    assert media[0].duration is None and media[0].mime_type is None
    assert media[0].source_material_id == material.id
    assert reference.source_name == "Video Wire"
    assert reference.adapter_type == "youtube"
    assert reference.author == "Reporter"
    assert reference.content_hash is not None


def test_no_media_source_remains_empty() -> None:
    material, _ = _make_material_and_event()
    assert _material_media(material) == []
