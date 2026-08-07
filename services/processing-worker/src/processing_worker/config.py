from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field


class Settings(BaseAppSettings):
    """Processing-worker settings. `instance_type` defaults to `integrator`
    since this worker only ever runs as part of an integrator installation."""

    instance_type: InstanceType = InstanceType.INTEGRATOR

    poll_interval_seconds: float = Field(
        default=15.0, alias="PROCESSING_WORKER_POLL_INTERVAL_SECONDS"
    )
    batch_size: int = Field(default=50, alias="PROCESSING_WORKER_BATCH_SIZE")
    ai_providers: str = Field(default="fake", alias="AI_PROVIDERS")
    ai_max_attempts_per_provider: int = Field(default=2, alias="AI_MAX_ATTEMPTS_PER_PROVIDER")

    @classmethod
    def from_env(cls) -> Settings:
        # pydantic-settings sources required fields (instance_id, database_url)
        # from the environment at runtime; mypy cannot see that, hence the ignore.
        return cls()  # type: ignore[call-arg]
