"""Production operations API: health details, alerts, jobs, and DLQ replay."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from common.auth import require_permission
from common.db import ping
from common.health import ping_redis
from common.observability import METRICS
from fastapi import APIRouter, Depends, HTTPException, Request
from site_domain.models import DeadLetter, DistributionJob, UnifiedJob
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

router = APIRouter(prefix="/api/v1/admin/system", tags=["system"])
JOB_STATUSES = ("scheduled", "processing", "retry_wait", "succeeded", "failed", "dlq", "cancelled")


def build_job_metrics_collector(
    factory: async_sessionmaker[AsyncSession],
) -> Callable[[], Awaitable[None]]:
    async def collect() -> None:
        async with factory() as session:
            rows = (
                await session.execute(
                    select(UnifiedJob.status, func.count()).group_by(UnifiedJob.status)
                )
            ).all()
        counts = {status: count for status, count in rows}
        for status in JOB_STATUSES:
            METRICS.gauge("background_jobs", float(counts.get(status, 0)), status=status)

    return collect


@router.get("/status", dependencies=[Depends(require_permission("system:read"))])
async def system_status(request: Request) -> dict[str, Any]:
    database = "ok"
    redis = "not_required"
    storage = "ok"
    try:
        await ping(request.app.state.db_engine)
    except Exception:
        database = "unavailable"
    if request.app.state.settings.readiness_require_redis:
        try:
            await ping_redis(request.app.state.settings.redis_url)
            redis = "ok"
        except Exception:
            redis = "unavailable"
    try:
        await request.app.state.object_storage.ensure_bucket()
    except Exception:
        storage = "unavailable"
    async with request.app.state.session_factory() as session:
        dlq_count = await session.scalar(
            select(func.count()).select_from(UnifiedJob).where(UnifiedJob.status == "dlq")
        )
        processing_count = await session.scalar(
            select(func.count()).select_from(UnifiedJob).where(UnifiedJob.status == "processing")
        )
    METRICS.gauge("background_jobs", float(dlq_count or 0), status="dlq")
    METRICS.gauge("background_jobs", float(processing_count or 0), status="processing")
    return {
        "status": "ok"
        if database == storage == "ok" and redis in {"ok", "not_required"}
        else "degraded",
        "components": {
            "database": database,
            "redis": redis,
            "object_storage": storage,
        },
        "jobs": {"processing": processing_count or 0, "dlq": dlq_count or 0},
        "version": request.app.state.settings.app_version,
    }


@router.get("/alerts", dependencies=[Depends(require_permission("system:read"))])
async def alerts(request: Request) -> list[dict[str, str]]:
    async with request.app.state.session_factory() as session:
        dlq_count = await session.scalar(
            select(func.count()).select_from(UnifiedJob).where(UnifiedJob.status == "dlq")
        )
    if dlq_count:
        return [{"code": "JOB_DLQ_NONEMPTY", "severity": "warning", "value": str(dlq_count)}]
    return []


@router.get("/jobs", dependencies=[Depends(require_permission("jobs:manage"))])
async def jobs(request: Request) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        rows = (
            await session.execute(
                select(UnifiedJob).order_by(UnifiedJob.created_at.desc()).limit(200)
            )
        ).scalars()
        return [_job(row) for row in rows]


@router.get("/dlq", dependencies=[Depends(require_permission("jobs:manage"))])
async def dead_letters(request: Request) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        rows = (
            await session.execute(
                select(DeadLetter, UnifiedJob)
                .join(UnifiedJob, UnifiedJob.id == DeadLetter.job_id)
                .where(DeadLetter.resolved_at.is_(None))
                .order_by(DeadLetter.created_at.desc())
            )
        ).all()
        return [
            {
                "id": str(letter.id),
                "job_id": str(job.id),
                "queue": job.queue,
                "kind": job.kind,
                "reason_code": letter.reason_code,
                "replay_count": letter.replay_count,
                "created_at": letter.created_at,
            }
            for letter, job in rows
        ]


@router.post("/dlq/{letter_id}/replay", dependencies=[Depends(require_permission("jobs:manage"))])
async def replay_dead_letter(letter_id: uuid.UUID, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        letter = await session.get(DeadLetter, letter_id)
        if letter is None or letter.resolved_at is not None:
            raise HTTPException(404, "active dead letter not found")
        job = await session.get(UnifiedJob, letter.job_id)
        if job is None:
            raise HTTPException(409, "dead letter job is unavailable")
        distribution = (
            await session.execute(
                select(DistributionJob).where(DistributionJob.unified_job_id == job.id)
            )
        ).scalar_one_or_none()
        if distribution is None:
            raise HTTPException(409, "job kind does not support manual replay")
        now = datetime.now(UTC)
        job.status = "scheduled"
        job.max_attempts = job.attempt_count + 1
        job.next_attempt_at = now
        job.error_code = None
        job.error_message = None
        job.completed_at = None
        job.lease_owner = None
        job.lease_expires_at = None
        distribution.status = "scheduled"
        distribution.max_attempts = distribution.attempt_count + 1
        distribution.next_attempt_at = now
        distribution.error_code = None
        distribution.error_message = None
        distribution.lease_owner = None
        distribution.lease_expires_at = None
        letter.replay_count += 1
        letter.replayed_at = now
        letter.resolved_at = now
        await session.commit()
        return _job(job)


def _job(row: UnifiedJob) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "queue": row.queue,
        "kind": row.kind,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "max_attempts": row.max_attempts,
        "next_attempt_at": row.next_attempt_at,
        "lease_expires_at": row.lease_expires_at,
        "error_code": row.error_code,
        "created_at": row.created_at,
    }
