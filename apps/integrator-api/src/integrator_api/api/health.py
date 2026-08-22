"""Liveness/readiness endpoints.

Per docs/02_SYSTEM_ARCHITECTURE.md §11 the health endpoint must not leak
secrets, SQL errors or internal addresses — readiness failures are reported
as a generic unavailable status only.
"""

from __future__ import annotations

from common.db import ping
from common.logging import get_logger
from fastapi import APIRouter, Request, Response, status

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(request: Request, response: Response) -> dict[str, str]:
    engine = request.app.state.db_engine
    try:
        await ping(engine)
    except Exception:
        logger.warning("readiness_check_failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ok"}
