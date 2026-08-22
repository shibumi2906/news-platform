from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field


class Settings(BaseAppSettings):
    """Delivery-worker settings. `instance_type` defaults to `integrator`
    since this worker only ever runs as part of an integrator installation."""

    instance_type: InstanceType = InstanceType.INTEGRATOR

    http_timeout_seconds: float = Field(default=10.0, alias="DELIVERY_WORKER_HTTP_TIMEOUT_SECONDS")
    batch_size: int = Field(default=50, alias="DELIVERY_WORKER_BATCH_SIZE")
    poll_interval_seconds: float = Field(
        default=15.0, alias="DELIVERY_WORKER_POLL_INTERVAL_SECONDS"
    )

    @classmethod
    def from_env(cls) -> Settings:
        # pydantic-settings sources required fields (instance_id, database_url)
        # from the environment at runtime; mypy cannot see that, hence the ignore.
        return cls()  # type: ignore[call-arg]
