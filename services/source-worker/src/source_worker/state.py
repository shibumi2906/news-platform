from __future__ import annotations

from uuid import UUID

from integrator_domain.models import Source, SourceRun
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
            source.status = "error"
            source.last_error = error
            source.consecutive_failures += 1
        elif source is not None and status in {"succeeded", "not_modified"}:
            source.status = "active"
            source.last_error = None
            source.consecutive_failures = 0
        session.add(
            SourceRun(source_id=source_id, status=status, error=error, created_count=created)
        )
