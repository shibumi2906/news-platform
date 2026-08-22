from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field


class Settings(BaseAppSettings):
    """Source-worker settings. `instance_type` defaults to `integrator` since
    this worker only ever runs as part of an integrator installation."""

    instance_type: InstanceType = InstanceType.INTEGRATOR

    http_timeout_seconds: float = Field(default=10.0, alias="SOURCE_WORKER_HTTP_TIMEOUT_SECONDS")
    http_user_agent: str = Field(
        default="news-platform-source-worker/0.1", alias="SOURCE_WORKER_USER_AGENT"
    )
    max_candidates_per_poll: int = Field(
        default=200, alias="SOURCE_WORKER_MAX_CANDIDATES_PER_POLL"
    )
    poll_interval_seconds: float = Field(
        default=300.0, alias="SOURCE_WORKER_POLL_INTERVAL_SECONDS"
    )

    @classmethod
    def from_env(cls) -> Settings:
        # pydantic-settings sources required fields (instance_id, database_url)
        # from the environment at runtime; mypy cannot see that, hence the ignore.
        return cls()  # type: ignore[call-arg]
