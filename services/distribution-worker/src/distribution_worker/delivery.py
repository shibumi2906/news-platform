"""Delivery state machine, retry/backoff, attempt audit, and DLQ handling."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from common.logging import get_logger
from site_domain.models import DistributionAttempt, DistributionChannel, DistributionJob
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from distribution_worker.adapters import DistributionAdapter, DistributionError

logger = get_logger(__name__)


async def process_due_jobs(
    session_factory: async_sessionmaker[AsyncSession],
    adapters: dict[str, DistributionAdapter],
    *,
    batch_size: int,
    retry_base_seconds: int,
) -> dict[str, int]:
    stats = {"delivered": 0, "retrying": 0, "dlq": 0, "failed": 0}
    async with session_factory() as session:
        for _ in range(batch_size):
            job = (
                await session.execute(
                    select(DistributionJob)
                    .where(
                        DistributionJob.status.in_({"scheduled", "retry_wait"}),
                        DistributionJob.next_attempt_at <= datetime.now(UTC),
                    )
                    .order_by(DistributionJob.next_attempt_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if job is None:
                break
            channel = await session.get(DistributionChannel, job.channel_id)
            if channel is None or not channel.is_active:
                await _record_failure(
                    session,
                    job,
                    "channel_unavailable",
                    retryable=False,
                    latency_ms=0,
                    retry_base_seconds=retry_base_seconds,
                )
                stats["failed"] += 1
                continue
            adapter = adapters.get(channel.kind)
            if adapter is None:
                await _record_failure(
                    session,
                    job,
                    "adapter_not_configured",
                    retryable=False,
                    latency_ms=0,
                    retry_base_seconds=retry_base_seconds,
                )
                stats["failed"] += 1
                continue
            job.status = "processing"
            started = time.perf_counter()
            try:
                result = await adapter.publish(
                    payload=job.payload,
                    config=channel.config,
                    credential_ref=channel.credential_ref,
                    idempotency_key=job.idempotency_key,
                )
            except DistributionError as exc:
                latency = max(1, int((time.perf_counter() - started) * 1000))
                outcome = await _record_failure(
                    session,
                    job,
                    exc.code,
                    retryable=exc.retryable,
                    latency_ms=latency,
                    retry_base_seconds=retry_base_seconds,
                )
                stats[outcome] += 1
                continue
            latency = max(1, int((time.perf_counter() - started) * 1000))
            job.attempt_count += 1
            job.status = "delivered"
            job.delivered_at = datetime.now(UTC)
            job.external_publication_id = result.external_id
            job.external_url = result.external_url
            job.error_code = None
            job.error_message = None
            session.add(
                DistributionAttempt(
                    job_id=job.id,
                    attempt_number=job.attempt_count,
                    status="succeeded",
                    provider_request_id=result.provider_request_id,
                    latency_ms=latency,
                )
            )
            await session.commit()
            stats["delivered"] += 1
            logger.info(
                "distribution_delivered",
                job_id=str(job.id),
                channel_kind=channel.kind,
                latency_ms=latency,
            )
    return stats


async def _record_failure(
    session: AsyncSession,
    job: DistributionJob,
    code: str,
    *,
    retryable: bool,
    latency_ms: int,
    retry_base_seconds: int,
) -> str:
    job.attempt_count += 1
    exhausted = job.attempt_count >= job.max_attempts
    if retryable and not exhausted:
        job.status = "retry_wait"
        job.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=retry_base_seconds * (2 ** (job.attempt_count - 1))
        )
        attempt_status = "retryable_error"
        outcome = "retrying"
    elif retryable:
        job.status = "dlq"
        attempt_status = "retryable_error"
        outcome = "dlq"
    else:
        job.status = "failed"
        attempt_status = "permanent_error"
        outcome = "failed"
    job.error_code = code
    job.error_message = "Delivery failed; inspect structured diagnostics and attempt history."
    session.add(
        DistributionAttempt(
            job_id=job.id,
            attempt_number=job.attempt_count,
            status=attempt_status,
            latency_ms=latency_ms,
            error_code=code,
            diagnostics="provider response and publication payload intentionally omitted",
        )
    )
    await session.commit()
    logger.warning(
        "distribution_attempt_failed", job_id=str(job.id), error_code=code, outcome=outcome
    )
    return outcome
