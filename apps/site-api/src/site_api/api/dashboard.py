"""Operator controls for the Site-owned Dashboard exporter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from common.auth import require_permission
from fastapi import APIRouter, Depends, Request
from site_domain.models import DashboardOutbox
from sqlalchemy import func, select

from site_api.dashboard import export_due, reconcile

router = APIRouter(prefix="/api/v1/admin/dashboard", tags=["dashboard"])


@router.get("/status", dependencies=[Depends(require_permission("system:read"))])
async def status(request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        rows = (
            await session.execute(
                select(DashboardOutbox.status, func.count()).group_by(DashboardOutbox.status)
            )
        ).all()
    return {"enabled": bool(request.app.state.settings.dashboard_url), "outbox": dict(rows)}


@router.post("/export", dependencies=[Depends(require_permission("jobs:manage"))])
async def export(request: Request) -> dict[str, int]:
    settings = request.app.state.settings
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await export_due(
            request.app.state.session_factory,
            dashboard_url=settings.dashboard_url,
            dashboard_key=(
                settings.dashboard_key.get_secret_value() if settings.dashboard_key else None
            ),
            site_instance_id=str(settings.instance_id),
            client=client,
            batch_size=100,
            retry_base_seconds=settings.dashboard_retry_base_seconds,
        )


@router.post("/reconcile", dependencies=[Depends(require_permission("jobs:manage"))])
async def reconcile_recent(request: Request) -> dict[str, int]:
    now = datetime.now(UTC)
    async with request.app.state.session_factory() as session:
        created = await reconcile(session, since=now - timedelta(days=1), until=now)
    return {"created": created}
