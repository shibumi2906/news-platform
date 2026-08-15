from __future__ import annotations
# ruff: noqa

from uuid import UUID

from datetime import timedelta
from common.time import utc_now

from integrator_domain.models import Source, SourceRun, SourceStateAudit
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def record_run(
    session_factory: async_sessionmaker[AsyncSession],
    source_id: UUID,
    status: str,
    created: int,
    error: str | None,
) -> None:
    async with session_factory() as session, session.begin():
        source = await session.get(Source, source_id)
        if source is not None and status == "failed":
            previous = source.health_status
            source.last_error = error
            source.consecutive_failures += 1
            pause_after = int(source.config.get("pause_after_failures", 5))
            source.health_status = "paused" if source.consecutive_failures >= pause_after else "degraded"
            source.status = "paused" if source.health_status == "paused" else "error"
            source.health_reason = error
            delay = min(3600, 30 * (2 ** min(source.consecutive_failures, 6)))
            source.next_retry_at = utc_now() + timedelta(seconds=delay)
            if source.health_status == "paused":
                source.is_active = False
            session.add(SourceStateAudit(source_id=source_id, previous_status=previous, status=source.health_status, reason=error, diagnostics={"failures": source.consecutive_failures, "retry_seconds": delay}))
        elif source is not None and status in {"succeeded", "not_modified"}:
            previous = source.health_status
            source.status = "active"
            source.health_status = "healthy"
            source.health_reason = None
            source.last_error = None
            source.consecutive_failures = 0
            source.last_success_at = utc_now()
            source.next_retry_at = None
            if previous != "healthy":
                session.add(SourceStateAudit(source_id=source_id, previous_status=previous, status="healthy", reason="recovered", diagnostics={}))
        session.add(
            SourceRun(source_id=source_id, status=status, error=error, created_count=created)
        )
