from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from common.db import create_engine, create_session_factory
from common.errors import DomainError, ErrorDetail, ErrorEnvelope
from common.logging import configure_logging, get_logger
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        envelope = ErrorEnvelope(
            error=ErrorDetail(code=exc.code, message=exc.message, details=exc.details)
        )
        return JSONResponse(status_code=exc.status_code, content=envelope.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                code="validation_error",
                message="request validation failed",
                details={"errors": jsonable_encoder(exc.errors())},
            )
        )
        return JSONResponse(status_code=422, content=envelope.model_dump(mode="json"))

    app.include_router(health_router)
    app.include_router(ingestion_router)
    return app
