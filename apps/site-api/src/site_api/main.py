from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from common.db import create_engine, create_session_factory
from common.errors import DomainError, ErrorDetail, ErrorEnvelope
from common.logging import (
    bind_correlation_id,
    bind_trace_id,
    configure_logging,
    get_correlation_id,
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
from common.observability import (
    router as metrics_router,
)
from common.rate_limit import SlidingWindowLimiter
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from site_api.api.distribution import router as distribution_router
from site_api.api.editorial import router as editorial_router
from site_api.api.health import router as health_router
from site_api.api.ingestion import router as ingestion_router
from site_api.api.media import router as media_router
from site_api.api.read_models import admin_router, public_router
from site_api.api.security import admin_router as security_admin_router
from site_api.api.security import router as security_router
from site_api.api.system import router as system_router
from site_api.config import Settings
from site_api.media_generation import FakeImageProvider, MediaGateway
from site_api.security_service import build_session_validator, ensure_security_seed, write_audit
from site_api.storage import S3ObjectStorage

logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.db_engine = create_engine(settings.database_url)
        app.state.session_factory = create_session_factory(app.state.db_engine)
        app.state.object_storage = S3ObjectStorage(
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key.get_secret_value(),
            secret_key=settings.s3_secret_key.get_secret_value(),
            bucket=settings.s3_bucket,
            region=settings.s3_region,
        )
        app.state.media_gateway = MediaGateway(
            [FakeImageProvider()], attempts_per_provider=settings.media_attempts_per_provider
        )
        app.state.admin_session_validator = build_session_validator(
            app.state.session_factory, idle_seconds=settings.admin_session_idle_seconds
        )
        if settings.admin_bootstrap_username and settings.admin_bootstrap_password:
            async with app.state.session_factory() as session:
                await ensure_security_seed(
                    session,
                    username=settings.admin_bootstrap_username,
                    password=settings.admin_bootstrap_password.get_secret_value(),
                )
        logger.info(
            "startup",
            instance_id=settings.instance_id,
            instance_type=settings.instance_type.value,
            app_version=settings.app_version,
        )
        yield
        await app.state.object_storage.close()
        await app.state.db_engine.dispose()

    app = FastAPI(title="Site API", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.login_limiter = SlidingWindowLimiter(
        limit=settings.auth_login_attempts_per_minute, window_seconds=60
    )
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
            context = getattr(request.state, "auth_context", None)
            if context is not None and request.method not in {"GET", "HEAD", "OPTIONS"}:
                try:
                    await write_audit(
                        request.app.state.session_factory,
                        context=context,
                        action=f"{request.method} {request.url.path}",
                        resource_type=request.url.path.split("/")[3]
                        if len(request.url.path.split("/")) > 3
                        else "api",
                        outcome="success" if response.status_code < 400 else "rejected",
                        status_code=response.status_code,
                    )
                except Exception:
                    logger.exception("audit_write_failed")
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
    app.include_router(metrics_router)
    app.include_router(ingestion_router)
    app.include_router(editorial_router)
    app.include_router(distribution_router)
    app.include_router(media_router)
    app.include_router(security_router)
    app.include_router(security_admin_router)
    app.include_router(system_router)
    app.include_router(public_router)
    app.include_router(admin_router)
    return app
