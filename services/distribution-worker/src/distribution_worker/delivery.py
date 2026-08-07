"""Delivery state machine, retry/backoff, attempt audit, and DLQ handling."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

from common.logging import (
    bind_correlation_id,
    get_logger,
    new_correlation_id,
    reset_correlation_id,
)
from common.retry import RetryPolicy
from site_domain.models import (
    DeadLetter,
    DistributionAttempt,
    DistributionChannel,
    DistributionJob,
    UnifiedJob,
    UnifiedJobAttempt,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from distribution_worker.adapters import DistributionAdapter, DistributionError

logger = get_logger(__name__)


async def process_due_jobs(
    session_factory: async_sessionmaker[AsyncSession],
    adapters: dict[str, DistributionAdapter],
    *,
    batch_size: int,
    retry_base_seconds: int,
    lease_seconds: int = 120,
) -> dict[str, int]:
    stats = {"delivered": 0, "retrying": 0, "dlq": 0, "failed": 0}
    worker_id = uuid.uuid4().hex
    async with session_factory() as session:
        for _ in range(batch_size):
            now = datetime.now(UTC)
            job = (
                await session.execute(
                    select(DistributionJob)
                    .where(
                        or_(
                            and_(
                                DistributionJob.status.in_({"scheduled", "retry_wait"}),
                                DistributionJob.next_attempt_at <= now,
                            ),
                            and_(
                                DistributionJob.status == "processing",
                                DistributionJob.lease_expires_at <= now,
                            ),
                        )
                    )
                    .order_by(DistributionJob.next_attempt_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if job is None:
                break
            if job.status == "processing":
                logger.warning("distribution_lease_recovered", job_id=str(job.id))
            job.status = "processing"
            job.lease_owner = worker_id
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
            unified = await _unified(session, job)
            correlation_token = bind_correlation_id(
                unified.correlation_id
                if unified and unified.correlation_id
                else new_correlation_id()
            )
            if unified is not None:
                unified.status = "processing"
                unified.lease_owner = worker_id
                unified.lease_expires_at = job.lease_expires_at
            await session.commit()
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
                reset_correlation_id(correlation_token)
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
                reset_correlation_id(correlation_token)
                continue
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
                reset_correlation_id(correlation_token)
                continue
            except Exception:
                reset_correlation_id(correlation_token)
                raise
            latency = max(1, int((time.perf_counter() - started) * 1000))
            job.attempt_count += 1
            job.status = "delivered"
            job.delivered_at = datetime.now(UTC)
            job.external_publication_id = result.external_id
            job.external_url = result.external_url
            job.error_code = None
            job.error_message = None
            job.lease_owner = None
            job.lease_expires_at = None
            session.add(
                DistributionAttempt(
                    job_id=job.id,
                    attempt_number=job.attempt_count,
                    status="succeeded",
                    provider_request_id=result.provider_request_id,
                    latency_ms=latency,
                )
            )
            if unified is not None:
                unified.status = "succeeded"
                unified.attempt_count = job.attempt_count
                unified.completed_at = job.delivered_at
                unified.lease_owner = None
                unified.lease_expires_at = None
                session.add(
                    UnifiedJobAttempt(
                        job_id=unified.id,
                        attempt_number=job.attempt_count,
                        status="succeeded",
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
            reset_correlation_id(correlation_token)
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
            seconds=RetryPolicy(base_seconds=retry_base_seconds).delay(job.attempt_count)
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
    job.lease_owner = None
    job.lease_expires_at = None
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
    unified = await _unified(session, job)
    if unified is not None:
        unified.status = job.status
        unified.attempt_count = job.attempt_count
        unified.next_attempt_at = job.next_attempt_at
        unified.error_code = code
        unified.error_message = job.error_message
        unified.lease_owner = None
        unified.lease_expires_at = None
        session.add(
            UnifiedJobAttempt(
                job_id=unified.id,
                attempt_number=job.attempt_count,
                status=attempt_status,
                latency_ms=latency_ms,
                error_code=code,
                diagnostics="provider payload intentionally omitted",
            )
        )
        if outcome == "dlq":
            dead_letter = (
                await session.execute(select(DeadLetter).where(DeadLetter.job_id == unified.id))
            ).scalar_one_or_none()
            if dead_letter is None:
                session.add(
                    DeadLetter(
                        job_id=unified.id,
                        reason_code=code,
                        diagnostics="Exhausted retry policy; payload intentionally omitted.",
                    )
                )
            else:
                dead_letter.reason_code = code
                dead_letter.diagnostics = (
                    "Exhausted retry policy; payload intentionally omitted."
                )
                dead_letter.resolved_at = None
                dead_letter.replayed_at = None
    await session.commit()
    logger.warning(
        "distribution_attempt_failed", job_id=str(job.id), error_code=code, outcome=outcome
    )
    return outcome


async def _unified(session: AsyncSession, job: DistributionJob) -> UnifiedJob | None:
    if job.unified_job_id is None:
        return None
    return await session.get(UnifiedJob, job.unified_job_id)
