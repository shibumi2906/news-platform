"""Outbox relay: delivers `canonical_news_package.created` events to every
active `SiteConnection` (ADR-003, ADR-006).

Stage 1B scope reduction (explicitly approved, mirrors `connection_filter`
being unbuilt): every active connection receives every package, there is no
topic/language/region filtering yet.

Unlike `processing_worker.processing`, a delivery outbox row that fails one
or more connections is left `pending` rather than marked `failed`: the next
scheduled poll retries it, and per-connection idempotency (`Delivery` keyed
on `(connection_id, idempotency_key)`) means already-delivered connections
are skipped on retry. This gives at-least-once delivery with backoff for
free from the poll interval, without a separate DLQ/manual-retry mechanism
(explicitly out of scope for Stage 1B — no admin UI). Only a permanently
unrecoverable row (its package went missing) is marked `failed`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx
from common.logging import get_logger
from integrator_domain.models import (
    CanonicalNewsPackage,
    Delivery,
    DeliveryAttempt,
    OutboxEvent,
    SiteConnection,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from delivery_worker.client import send_package
from delivery_worker.packaging import package_row_to_envelope

CANONICAL_PACKAGE_CREATED = "canonical_news_package.created"

logger = get_logger(__name__)


@dataclass
class DeliveryStats:
    delivered: int = 0
    retrying: int = 0
    skipped_duplicate: int = 0
    failed: int = 0


async def process_pending_deliveries(
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    *,
    batch_size: int,
    http_timeout_seconds: float,
) -> DeliveryStats:
    stats = DeliveryStats()

    async with session_factory() as session:
        result = await session.execute(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.event_type == CANONICAL_PACKAGE_CREATED,
            )
            .order_by(OutboxEvent.created_at)
            .limit(batch_size)
        )
        pending_ids = [row[0] for row in result.all()]

    for outbox_event_id in pending_ids:
        outcome = await _process_one(
            session_factory, client, outbox_event_id, http_timeout_seconds=http_timeout_seconds
        )
        if outcome == "delivered":
            stats.delivered += 1
        elif outcome == "retrying":
            stats.retrying += 1
        elif outcome == "duplicate":
            stats.skipped_duplicate += 1
        else:
            stats.failed += 1

    return stats


async def _process_one(
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    outbox_event_id: UUID,
    *,
    http_timeout_seconds: float,
) -> str:
    async with session_factory() as session, session.begin():
        outbox_event = await session.get(OutboxEvent, outbox_event_id)
        if outbox_event is None or outbox_event.status != "pending":
            return "duplicate"

        package_id = UUID(outbox_event.payload["package_id"])
        package_version = int(outbox_event.payload["package_version"])

        package_result = await session.execute(
            select(CanonicalNewsPackage).where(
                CanonicalNewsPackage.package_id == package_id,
                CanonicalNewsPackage.package_version == package_version,
            )
        )
        package = package_result.scalar_one_or_none()
        if package is None:
            logger.error(
                "delivery_package_missing",
                outbox_event_id=str(outbox_event_id),
                package_id=str(package_id),
                package_version=package_version,
            )
            outbox_event.status = "failed"
            return "failed"

        connections_result = await session.execute(
            select(SiteConnection).where(SiteConnection.is_active)
        )
        connections = connections_result.scalars().all()
        if not connections:
            outbox_event.status = "processed"
            return "delivered"

        envelope = package_row_to_envelope(package)
        body = envelope.model_dump_json().encode("utf-8")

        all_delivered = True
        for connection in connections:
            delivered = await _deliver_to_connection(
                session,
                client,
                connection=connection,
                package=package,
                body=body,
                http_timeout_seconds=http_timeout_seconds,
            )
            all_delivered = all_delivered and delivered

        if all_delivered:
            outbox_event.status = "processed"
            return "delivered"
        return "retrying"


async def _deliver_to_connection(
    session: AsyncSession,
    client: httpx.AsyncClient,
    *,
    connection: SiteConnection,
    package: CanonicalNewsPackage,
    body: bytes,
    http_timeout_seconds: float,
) -> bool:
    idempotency_key = f"{package.package_id}:{package.package_version}"

    delivery_result = await session.execute(
        select(Delivery).where(
            Delivery.connection_id == connection.id, Delivery.idempotency_key == idempotency_key
        )
    )
    delivery = delivery_result.scalar_one_or_none()
    if delivery is None:
        delivery = Delivery(
            package_id=package.package_id,
            package_version=package.package_version,
            connection_id=connection.id,
            idempotency_key=idempotency_key,
            status="pending",
        )
        session.add(delivery)
        await session.flush()

    if delivery.status == "delivered":
        return True

    attempts_result = await session.execute(
        select(func.count())
        .select_from(DeliveryAttempt)
        .where(DeliveryAttempt.delivery_id == delivery.id)
    )
    attempt_number = attempts_result.scalar_one() + 1

    result = await send_package(
        client,
        connection_id=connection.id,
        delivery_url=connection.delivery_url,
        hmac_secret=connection.hmac_secret,
        idempotency_key=idempotency_key,
        body=body,
        timeout_seconds=http_timeout_seconds,
    )

    session.add(
        DeliveryAttempt(
            delivery_id=delivery.id,
            attempt_number=attempt_number,
            status=result.status,
            response_status_code=result.response_status_code,
            error={"message": result.error} if result.error else None,
        )
    )
    delivery.status = result.status

    if result.status != "delivered":
        logger.warning(
            "delivery_attempt_failed",
            connection_id=str(connection.id),
            package_id=str(package.package_id),
            package_version=package.package_version,
            attempt_number=attempt_number,
            error=result.error,
        )

    return result.status == "delivered"
