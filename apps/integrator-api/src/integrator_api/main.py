from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from common.db import create_engine
from common.logging import configure_logging, get_logger
from fastapi import FastAPI

from integrator_api.api.health import router as health_router
from integrator_api.config import Settings

logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.db_engine = create_engine(settings.database_url)
        logger.info(
            "startup",
            instance_id=settings.instance_id,
            instance_type=settings.instance_type.value,
            app_version=settings.app_version,
        )
        yield
        await app.state.db_engine.dispose()

    app = FastAPI(title="Integrator API", version=settings.app_version, lifespan=lifespan)
    app.include_router(health_router)
    return app
