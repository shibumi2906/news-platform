from __future__ import annotations
# ruff: noqa: I001

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import httpx
from common.db import create_engine, create_session_factory
from common.logging import (
    bind_correlation_id,
    bind_trace_id,
    configure_logging,
    get_logger,
    new_correlation_id,
    reset_correlation_id,
    reset_trace_id,
)
from common.observability import (
    request_finished,
    request_started,
    trace_context,
)
from common.rate_limit import SlidingWindowLimiter
from common.observability import (
    router as metrics_router,
)
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from integrator_api.api.ai_admin import router as ai_admin_router
from integrator_api.api.event_intelligence import router as event_intelligence_router
from integrator_api.api.parser_lab import router as parser_lab_router
from integrator_api.api.health import router as health_router
from integrator_api.api.integration import router as integration_router
from integrator_api.api.operations import router as operations_router
from integrator_api.api.materials import router as materials_router
from integrator_api.api.relevance import router as relevance_router
from integrator_api.api.site_feed import router as site_feed_router
from integrator_api.api.sources import router as sources_router
from integrator_api.config import Settings
from integrator_api.security import build_remote_session_validator

logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.db_engine = create_engine(settings.database_url)
        app.state.session_factory = create_session_factory(app.state.db_engine)
        app.state.site_auth_client = httpx.AsyncClient(
            base_url=settings.site_api_url.rstrip("/"),
            timeout=settings.admin_introspection_timeout_seconds,
            trust_env=False,
        )
        service_token = (
            settings.admin_api_token.get_secret_value().split(",", maxsplit=1)[0].strip()
            if settings.admin_api_token is not None
            else ""
        )
        app.state.admin_session_validator = build_remote_session_validator(
            app.state.site_auth_client, service_token=service_token
        )
        logger.info(
            "startup",
            instance_id=settings.instance_id,
            instance_type=settings.instance_type.value,
            app_version=settings.app_version,
        )
        yield
        await app.state.site_auth_client.aclose()
        await app.state.db_engine.dispose()

    app = FastAPI(title="Integrator API", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.integration_limiter = SlidingWindowLimiter(limit=30, window_seconds=60)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[item.strip() for item in settings.allowed_hosts.split(",") if item.strip()],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            item.strip() for item in settings.allowed_origins.split(",") if item.strip()
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Admin-Session", "X-CSRF-Token", "X-Request-Id"],
    )

    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        supplied_id = request.headers.get("X-Request-Id")
        try:
            correlation_id = str(UUID(supplied_id)) if supplied_id else new_correlation_id()
        except ValueError:
            correlation_id = new_correlation_id()
        trace_id, response_traceparent = trace_context(request.headers.get("traceparent"))
        token = bind_correlation_id(correlation_id)
        trace_token = bind_trace_id(trace_id)
        started = request_started()
        response: Response | None = None
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled_request_exception", method=request.method, path=request.url.path
            )
            raise
        finally:
            status_code = response.status_code if response is not None else 500
            route = getattr(request.scope.get("route"), "path", request.url.path)
            request_finished(started, request.method, route, status_code)
            reset_correlation_id(token)
            reset_trace_id(trace_token)
        if response is None:
            raise RuntimeError("request completed without a response")
        response.headers["X-Request-Id"] = correlation_id
        response.headers["traceparent"] = response_traceparent
        return response

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(sources_router)
    app.include_router(ai_admin_router)
    app.include_router(event_intelligence_router)
    app.include_router(parser_lab_router)
    app.include_router(operations_router)
    app.include_router(materials_router)
    app.include_router(relevance_router)
    app.include_router(site_feed_router)
    app.include_router(integration_router)
    return app
