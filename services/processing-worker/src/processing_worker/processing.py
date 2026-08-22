"""Outbox relay: turns `source_material.ingested` events into
`CanonicalNewsPackage` rows and a `canonical_news_package.created` event for
the delivery-worker (ADR-006).

Stage 1B runs a single poller instance, so `pending` rows are claimed by a
plain `SELECT` rather than `SELECT ... FOR UPDATE SKIP LOCKED` — safe under
that assumption, and it keeps this code portable to the SQLite engine used
in tests. Revisit once processing-worker is scaled beyond one replica.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from common.logging import get_logger
from integrator_domain.models import CanonicalNewsPackage, Event, OutboxEvent, SourceMaterial
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from processing_worker.packaging import build_package_envelope, envelope_to_row

SOURCE_MATERIAL_INGESTED = "source_material.ingested"
CANONICAL_PACKAGE_CREATED = "canonical_news_package.created"

logger = get_logger(__name__)


@dataclass
class ProcessingStats:
    processed: int = 0
    skipped_duplicate: int = 0
    failed: int = 0


async def process_pending_events(
    session_factory: async_sessionmaker[AsyncSession], *, instance_id: UUID, batch_size: int
) -> ProcessingStats:
    stats = ProcessingStats()

    async with session_factory() as session:
        result = await session.execute(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.event_type == SOURCE_MATERIAL_INGESTED,
            )
            .order_by(OutboxEvent.created_at)
            .limit(batch_size)
        )
        pending_ids = [row[0] for row in result.all()]

    for outbox_event_id in pending_ids:
        outcome = await _process_one(session_factory, outbox_event_id, instance_id=instance_id)
        if outcome == "processed":
            stats.processed += 1
        elif outcome == "duplicate":
            stats.skipped_duplicate += 1
        else:
            stats.failed += 1

    return stats


async def _process_one(
    session_factory: async_sessionmaker[AsyncSession], outbox_event_id: UUID, *, instance_id: UUID
) -> str:
    async with session_factory() as session, session.begin():
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        if outbox_event is None or outbox_event.status != "pending":
            return "duplicate"

        source_material_id = UUID(outbox_event.payload["source_material_id"])
        event_id = UUID(outbox_event.payload["event_id"])

        material = await session.get(SourceMaterial, source_material_id)
        event = await session.get(Event, event_id)
        if material is None or event is None:
            logger.error(
                "processing_source_missing",
                outbox_event_id=str(outbox_event_id),
                source_material_id=str(source_material_id),
                event_id=str(event_id),
            )
            outbox_event.status = "failed"
            return "failed"

        existing_package = await session.execute(
            select(CanonicalNewsPackage.id).where(CanonicalNewsPackage.event_id == event.id)
        )
        if existing_package.first() is not None:
            outbox_event.status = "processed"
            return "duplicate"

        envelope = build_package_envelope(material, event, instance_id=instance_id)
        package = envelope_to_row(envelope)
        session.add(package)
        await session.flush()

        session.add(
            OutboxEvent(
                event_type=CANONICAL_PACKAGE_CREATED,
                payload={
                    "package_id": str(package.package_id),
                    "package_version": package.package_version,
                    "event_id": str(event.id),
                    "instance_id": str(instance_id),
                },
            )
        )
        outbox_event.status = "processed"
        return "processed"
