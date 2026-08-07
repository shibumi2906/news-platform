from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field


class Settings(BaseAppSettings):
    instance_type: InstanceType = InstanceType.SITE
    batch_size: int = Field(default=25, alias="DISTRIBUTION_WORKER_BATCH_SIZE")
    poll_interval_seconds: float = Field(default=10, alias="DISTRIBUTION_WORKER_POLL_SECONDS")
    http_timeout_seconds: float = Field(default=10, alias="DISTRIBUTION_HTTP_TIMEOUT_SECONDS")
    retry_base_seconds: int = Field(default=30, alias="DISTRIBUTION_RETRY_BASE_SECONDS")
    telegram_base_url: str = Field(default="https://api.telegram.org", alias="TELEGRAM_BASE_URL")

    @classmethod
    def from_env(cls) -> Settings:
        return cls()  # type: ignore[call-arg]
