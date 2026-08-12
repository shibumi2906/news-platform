"""Site-owned, idempotent export of aggregate-safe Dashboard metrics."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx
from common.observability import METRICS
from common.retry import RetryPolicy
from site_domain.models import (
    DashboardExportAttempt,
    DashboardOutbox,
    IncomingPackageVersion,
    Publication,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def enqueue_metric(
    session: AsyncSession,
    *,
    event_type: str,
    metric: str,
    occurred_at: datetime,
    idempotency_key: str,
    value: int = 1,
    dimensions: dict[str, str] | None = None,
) -> DashboardOutbox:
    """Add an export record without committing the caller's business transaction."""
    existing = await session.scalar(
        select(DashboardOutbox).where(DashboardOutbox.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    row = DashboardOutbox(
        event_type=event_type,
        metric=metric,
        occurred_at=occurred_at,
        dimensions=dimensions or {},
        value=value,
        idempotency_key=idempotency_key,
        status="scheduled",
        next_attempt_at=occurred_at,
    )
    session.add(row)
    await session.flush()
    return row


async def export_due(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    dashboard_url: str | None,
    dashboard_key: str | None,
    site_instance_id: str,
    client: httpx.AsyncClient,
    batch_size: int,
    retry_base_seconds: int,
) -> dict[str, int]:
    """Export due records. A missing Dashboard configuration is intentionally a no-op."""
    stats = {"exported": 0, "retrying": 0, "failed": 0}
    if not dashboard_url or not dashboard_key:
        return stats
    for _ in range(batch_size):
        async with session_factory() as session:
            now = datetime.now(UTC)
            row = (
                await session.execute(
                    select(DashboardOutbox)
                    .where(
                        or_(
                            and_(
                                DashboardOutbox.status.in_({"scheduled", "retry_wait"}),
                                DashboardOutbox.next_attempt_at <= now,
                            ),
                            and_(
                                DashboardOutbox.status == "processing",
                                DashboardOutbox.next_attempt_at <= now,
                            ),
                        )
                    )
                    .order_by(DashboardOutbox.next_attempt_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if row is None:
                break
            row.status = "processing"
            # A crashed exporter becomes eligible again after the same bounded lease.
            row.next_attempt_at = now + timedelta(seconds=120)
            await session.commit()
            payload = {
                "schema_version": "1.0",
                "site_instance_id": site_instance_id,
                "event_type": row.event_type,
                "metric": row.metric,
                "occurred_at": row.occurred_at.isoformat(),
                "period_start": row.period_start.isoformat() if row.period_start else None,
                "period_end": row.period_end.isoformat() if row.period_end else None,
                "dimensions": row.dimensions,
                "value": row.value,
            }
            started = time.perf_counter()
            response_status: int | None = None
            try:
                response = await client.post(
                    dashboard_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {dashboard_key}",
                        "Idempotency-Key": row.idempotency_key,
                    },
                )
                response_status = response.status_code
                retryable = response.status_code in {408, 429} or response.status_code >= 500
                success = 200 <= response.status_code < 300
            except httpx.RequestError:
                retryable, success = True, False
            latency_ms = max(1, int((time.perf_counter() - started) * 1000))
            async with session_factory() as update_session:
                current = await update_session.get(DashboardOutbox, row.id)
                if current is None:
                    continue
                current.attempt_count += 1
                if success:
                    current.status = "exported"
                    current.exported_at = datetime.now(UTC)
                    current.error_code = None
                    attempt_status, outcome = "succeeded", "exported"
                elif retryable:
                    current.status = "retry_wait"
                    current.next_attempt_at = datetime.now(UTC) + timedelta(
                        seconds=RetryPolicy(base_seconds=retry_base_seconds).delay(
                            current.attempt_count
                        )
                    )
                    current.error_code = "dashboard_temporarily_unavailable"
                    attempt_status, outcome = "retryable_error", "retrying"
                else:
                    current.status = "failed"
                    current.error_code = "dashboard_request_rejected"
                    attempt_status, outcome = "permanent_error", "failed"
                update_session.add(
                    DashboardExportAttempt(
                        outbox_id=current.id,
                        attempt_number=current.attempt_count,
                        status=attempt_status,
                        response_status=response_status,
                        diagnostics="Dashboard response body intentionally omitted.",
                    )
                )
                await update_session.commit()
            METRICS.increment("dashboard_exports_total", outcome=outcome)
            METRICS.increment("dashboard_export_duration_seconds_sum", latency_ms / 1000)
            stats[outcome] += 1
    return stats


async def reconcile(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
) -> int:
    """Restore absent outbox rows from Site-owned facts, without duplicating exports."""
    created = 0
    packages = (
        await session.execute(
            select(IncomingPackageVersion).where(
                IncomingPackageVersion.created_at >= since,
                IncomingPackageVersion.created_at < until,
            )
        )
    ).scalars()
    for package in packages:
        key = f"package_received:{package.id}"
        existing = await session.scalar(
            select(DashboardOutbox.id).where(DashboardOutbox.idempotency_key == key)
        )
        if existing:
            continue
        await enqueue_metric(
            session,
            event_type="package.received",
            metric="packages_received",
            occurred_at=package.created_at,
            idempotency_key=key,
        )
        created += 1
    publications = (
        await session.execute(
            select(Publication).where(
                Publication.status == "published",
                Publication.published_at >= since,
                Publication.published_at < until,
            )
        )
    ).scalars()
    for publication in publications:
        key = f"article_published:{publication.id}:{publication.active_article_version_id}"
        existing = await session.scalar(
            select(DashboardOutbox.id).where(DashboardOutbox.idempotency_key == key)
        )
        if existing:
            continue
        await enqueue_metric(
            session,
            event_type="article.published",
            metric="articles_published",
            occurred_at=publication.published_at or publication.created_at,
            idempotency_key=key,
        )
        created += 1
    await session.commit()
    return created
