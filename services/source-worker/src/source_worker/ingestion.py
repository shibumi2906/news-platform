"""Normalize/checkpoint step: persists `SourceCandidate` values as
`SourceMaterial` rows, per docs/05 §2 ("the adapter does not create an event
or write an article") the event and outbox write happen here, one layer up
from the RSS adapter.

Stage 1B scope reduction (explicitly approved): each `SourceMaterial` gets
its own 1:1 `Event` stub — see `integrator_domain.models.event`.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.hashing import sha256_hex
from contracts.source import SourceCandidate
from integrator_domain.models import Event, OutboxEvent, SourceMaterial
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass
class IngestionStats:
    created: int = 0
    duplicates: int = 0


async def ingest_candidates(
    session_factory: async_sessionmaker[AsyncSession],
    candidates: list[SourceCandidate],
) -> IngestionStats:
    stats = IngestionStats()
    for candidate in candidates:
        try:
            created = await _ingest_one(session_factory, candidate)
        except IntegrityError:
            # Unique constraint on (source_id, external_id) or
            # (source_id, canonical_url_hash) raced with a concurrent poll.
            created = False
        if created:
            stats.created += 1
        else:
            stats.duplicates += 1
    return stats


async def _ingest_one(
    session_factory: async_sessionmaker[AsyncSession], candidate: SourceCandidate
) -> bool:
    async with session_factory() as session, session.begin():
        if await _material_exists(session, candidate):
            return False

        material = SourceMaterial(
            source_id=candidate.source_id,
            external_id=candidate.external_id,
            url=candidate.url,
            canonical_url=candidate.canonical_url,
            canonical_url_hash=sha256_hex(candidate.canonical_url),
            title=candidate.title,
            excerpt=candidate.excerpt,
            body=candidate.body,
            author=candidate.author,
            language=candidate.language,
            published_at=candidate.published_at,
            source_updated_at=candidate.updated_at,
            fetched_at=candidate.fetched_at,
            raw=candidate.raw,
        )
        session.add(material)
        await session.flush()

        event = Event(source_material_id=material.id)
        session.add(event)
        await session.flush()

        session.add(
            OutboxEvent(
                event_type="source_material.ingested",
                payload={
                    "source_material_id": str(material.id),
                    "event_id": str(event.id),
                    "source_id": str(candidate.source_id),
                    "canonical_url": candidate.canonical_url,
                    "language": candidate.language,
                    "published_at": candidate.published_at.isoformat(),
                },
            )
        )
        return True


async def _material_exists(session: AsyncSession, candidate: SourceCandidate) -> bool:
    canonical_url_hash = sha256_hex(candidate.canonical_url)
    stmt = select(SourceMaterial.id).where(
        SourceMaterial.source_id == candidate.source_id,
        or_(
            SourceMaterial.external_id == candidate.external_id,
            SourceMaterial.canonical_url_hash == canonical_url_hash,
        ),
    )
    result = await session.execute(stmt)
    return result.first() is not None
