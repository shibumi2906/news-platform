from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from common.db import create_engine, create_session_factory
from common.logging import (
    bind_correlation_id,
    configure_logging,
    get_logger,
    new_correlation_id,
    reset_correlation_id,
)
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from integrator_api.api.ai_admin import router as ai_admin_router
from integrator_api.api.health import router as health_router
from integrator_api.api.operations import router as operations_router
from integrator_api.api.sources import router as sources_router
from integrator_api.config import Settings

logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.db_engine = create_engine(settings.database_url)
        app.state.session_factory = create_session_factory(app.state.db_engine)
        logger.info(
            "startup",
            instance_id=settings.instance_id,
            instance_type=settings.instance_type.value,
            app_version=settings.app_version,
        )
        yield
        await app.state.db_engine.dispose()

    app = FastAPI(title="Integrator API", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings

    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = new_correlation_id()
        token = bind_correlation_id(correlation_id)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled_request_exception", method=request.method, path=request.url.path
            )
            raise
        finally:
            reset_correlation_id(token)
        response.headers["X-Request-Id"] = correlation_id
        return response

    app.include_router(health_router)
    app.include_router(sources_router)
    app.include_router(ai_admin_router)
    app.include_router(operations_router)
    return app
