"""Operational read models consumed by Integrator Admin UI."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from common.auth import require_permission
from fastapi import APIRouter, Depends, Query, Request
from integrator_domain.models import AIOperationRun, CanonicalNewsPackage
from pydantic import BaseModel
from sqlalchemy import select

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["integrator-operations"],
    dependencies=[Depends(require_permission("system:read"))],
)


class AIRunOutput(BaseModel):
    id: UUID
    operation: str
    provider: str
    model: str
    status: str
    error_code: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    estimated_cost_usd: float
    created_at: datetime


class PackageOutput(BaseModel):
    id: UUID
    package_id: UUID
    package_version: int
    event_id: UUID
    title: str
    language: str
    languages: list[str]
    created_at: datetime


@router.get("/ai-runs", response_model=list[AIRunOutput])
async def list_ai_runs(
    request: Request,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AIRunOutput]:
    async with request.app.state.session_factory() as session:
        statement = select(AIOperationRun).order_by(AIOperationRun.created_at.desc()).limit(limit)
        if status is not None:
            statement = statement.where(AIOperationRun.status == status)
        rows = (await session.execute(statement)).scalars()
        return [
            AIRunOutput(
                id=row.id,
                operation=row.operation,
                provider=row.provider,
                model=row.model,
                status=row.status,
                error_code=row.error_code,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                latency_ms=row.latency_ms,
                estimated_cost_usd=row.estimated_cost_usd,
                created_at=row.created_at,
            )
            for row in rows
        ]


@router.get("/packages", response_model=list[PackageOutput])
async def list_packages(
    request: Request, limit: int = Query(default=50, ge=1, le=200)
) -> list[PackageOutput]:
    async with request.app.state.session_factory() as session:
        rows = (
            await session.execute(
                select(CanonicalNewsPackage)
                .order_by(CanonicalNewsPackage.created_at.desc())
                .limit(limit)
            )
        ).scalars()
        return [_package_output(row) for row in rows]


def _package_output(row: CanonicalNewsPackage) -> PackageOutput:
    content: dict[str, Any] = row.content
    return PackageOutput(
        id=row.id,
        package_id=row.package_id,
        package_version=row.package_version,
        event_id=row.event_id,
        title=_safe_text(content.get("title"), "Untitled package"),
        language=_safe_text(content.get("language"), "und"),
        languages=sorted({_safe_text(content.get("language"), "und"), *row.language_versions}),
        created_at=row.created_at,
    )


def _safe_text(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default
