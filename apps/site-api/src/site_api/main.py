from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from common.db import create_engine, create_session_factory
from common.errors import DomainError, ErrorDetail, ErrorEnvelope
from common.logging import (
    bind_correlation_id,
    configure_logging,
    get_correlation_id,
    get_logger,
    new_correlation_id,
    reset_correlation_id,
)
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from site_api.api.editorial import router as editorial_router
from site_api.api.health import router as health_router
from site_api.api.ingestion import router as ingestion_router
from site_api.config import Settings

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

    app = FastAPI(title="Site API", version=settings.app_version, lifespan=lifespan)

    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Client-supplied IDs are deliberately ignored: identifiers in logs
        # must not be a vehicle for arbitrary or personal data.
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

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        logger.warning("domain_request_rejected", code=exc.code, status_code=exc.status_code)
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                correlation_id=get_correlation_id(),
            )
        )
        return JSONResponse(status_code=exc.status_code, content=envelope.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("request_validation_failed")
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                code="validation_error",
                message="request validation failed",
                details={"errors": jsonable_encoder(exc.errors())},
                correlation_id=get_correlation_id(),
            )
        )
        return JSONResponse(status_code=422, content=envelope.model_dump(mode="json"))

    app.include_router(health_router)
    app.include_router(ingestion_router)
    app.include_router(editorial_router)
    return app
