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
from datetime import timedelta
from uuid import UUID

import httpx
from common.logging import get_logger
from common.observability import METRICS
from common.time import as_utc, utc_now
from integrator_domain.models import (
    CanonicalNewsPackage,
    Delivery,
    DeliveryAttempt,
    OutboxEvent,
    ReplayRequest,
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
    dead_lettered: int = 0


async def process_pending_deliveries(
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    *,
    batch_size: int,
    http_timeout_seconds: float,
    max_delivery_attempts: int = 10,
    retry_backoff_seconds: float = 0.0,
) -> DeliveryStats:
    stats = DeliveryStats()

    async with session_factory() as session:
        status_rows = await session.execute(
            select(Delivery.status, func.count()).group_by(Delivery.status)
        )
        status_counts: dict[str, int] = {
            status: count for status, count in status_rows.all()
        }
        for status in ("pending", "retrying", "delivered", "failed", "dead_lettered"):
            METRICS.gauge(
                "delivery_status", float(status_counts.get(status, 0)), status=status
            )
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
            session_factory,
            client,
            outbox_event_id,
            http_timeout_seconds=http_timeout_seconds,
            max_delivery_attempts=max_delivery_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        if outcome == "delivered":
            stats.delivered += 1
        elif outcome == "retrying":
            stats.retrying += 1
        elif outcome == "duplicate":
            stats.skipped_duplicate += 1
        elif outcome == "dead_lettered":
            stats.dead_lettered += 1
        else:
            stats.failed += 1

    return stats


async def _process_one(
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    outbox_event_id: UUID,
    *,
    http_timeout_seconds: float,
    max_delivery_attempts: int,
    retry_backoff_seconds: float,
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
            await _record_replay_outcome(session, outbox_event, "failed")
            METRICS.increment("delivery_outbox_total", status="failed")
            return "failed"

        connection_ids = {
            UUID(value) for value in outbox_event.payload.get("connection_ids", [])
        }
        connection_query = select(SiteConnection).where(
            SiteConnection.is_active, SiteConnection.delivery_mode == "push"
        )
        if connection_ids:
            connection_query = connection_query.where(SiteConnection.id.in_(connection_ids))
        connections_result = await session.execute(connection_query)
        connections = connections_result.scalars().all()
        if not connections:
            if connection_ids:
                outbox_event.status = "failed"
                await _record_replay_outcome(session, outbox_event, "failed")
                METRICS.increment("delivery_outbox_total", status="failed")
                return "failed"
            outbox_event.status = "processed"
            return "delivered"

        envelope = package_row_to_envelope(package)
        body = envelope.model_dump_json().encode("utf-8")

        outcomes: list[str] = []
        for connection in connections:
            outcome = await _deliver_to_connection(
                session,
                client,
                connection=connection,
                package=package,
                body=body,
                http_timeout_seconds=http_timeout_seconds,
                max_delivery_attempts=max_delivery_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                replay_request_id=outbox_event.payload.get("replay_request_id"),
            )
            outcomes.append(outcome)

        if all(outcome == "delivered" for outcome in outcomes):
            outbox_event.status = "processed"
            await _record_replay_outcome(session, outbox_event, "delivered")
            METRICS.increment("delivery_outbox_total", status="delivered")
            return "delivered"
        terminal = {"delivered", "dead_lettered"}
        if all(outcome in terminal for outcome in outcomes) and any(
            outcome == "dead_lettered" for outcome in outcomes
        ):
            outbox_event.status = "dead_lettered"
            await _record_replay_outcome(session, outbox_event, "failed")
            METRICS.increment("delivery_outbox_total", status="dead_lettered")
            return "dead_lettered"
        METRICS.increment("delivery_outbox_total", status="retrying")
        return "retrying"


async def _deliver_to_connection(
    session: AsyncSession,
    client: httpx.AsyncClient,
    *,
    connection: SiteConnection,
    package: CanonicalNewsPackage,
    body: bytes,
    http_timeout_seconds: float,
    max_delivery_attempts: int,
    retry_backoff_seconds: float,
    replay_request_id: object = None,
) -> str:
    wire_idempotency_key = f"{package.package_id}:{package.package_version}"
    idempotency_key = (
        f"{wire_idempotency_key}:replay:{replay_request_id}"
        if replay_request_id
        else wire_idempotency_key
    )

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
        return "delivered"

    if delivery.status == "dead_lettered":
        return "dead_lettered"
    now = utc_now()
    if delivery.next_attempt_at is not None and as_utc(delivery.next_attempt_at) > now:
        return "retrying"
    if delivery.attempt_budget_used >= max_delivery_attempts:
        delivery.status = "dead_lettered"
        delivery.dead_lettered_at = now
        METRICS.increment("delivery_attempt_total", status="dead_lettered")
        return "dead_lettered"

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
        signing_key_id=connection.active_key_id,
        idempotency_key=wire_idempotency_key,
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
    delivery.attempt_budget_used += 1
    delivery.last_error = result.error
    delivery.next_attempt_at = None

    if result.status != "delivered":
        if delivery.attempt_budget_used >= max_delivery_attempts:
            delivery.status = "dead_lettered"
            delivery.dead_lettered_at = now
        else:
            delivery.status = "retrying"
            delay = retry_backoff_seconds * (2 ** (delivery.attempt_budget_used - 1))
            delivery.next_attempt_at = now + timedelta(seconds=delay)

    if result.status != "delivered":
        logger.warning(
            "delivery_attempt_failed",
            connection_id=str(connection.id),
            package_id=str(package.package_id),
            package_version=package.package_version,
            attempt_number=attempt_number,
            error=result.error,
            signing_key_id=connection.active_key_id,
        )
    else:
        logger.info(
            "delivery_attempt_succeeded",
            connection_id=str(connection.id),
            package_id=str(package.package_id),
            package_version=package.package_version,
            signing_key_id=connection.active_key_id,
            replay=bool(replay_request_id),
        )
        if replay_request_id:
            METRICS.increment("delivery_replay_total", action="delivered")
    METRICS.increment("delivery_attempt_total", status=delivery.status)

    return "delivered" if result.status == "delivered" else delivery.status


async def _record_replay_outcome(
    session: AsyncSession, outbox_event: OutboxEvent, outcome: str
) -> None:
    raw_id = outbox_event.payload.get("replay_request_id")
    if not raw_id:
        return
    replay = await session.get(ReplayRequest, UUID(str(raw_id)))
    if replay is None:
        return
    if outcome == "delivered":
        replay.completed_count += 1
    else:
        replay.failed_count += 1
    finished = replay.completed_count + replay.failed_count >= replay.package_count
    if finished:
        replay.status = "completed" if replay.failed_count == 0 else "failed"
    else:
        replay.status = "running"
