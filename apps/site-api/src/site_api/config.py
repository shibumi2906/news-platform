from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field


class Settings(BaseAppSettings):
    """Site API settings. `instance_type` defaults to `site` since
    this application only ever runs as part of a site installation."""

    instance_type: InstanceType = InstanceType.SITE

    #: docs/14 §2: requests with a timestamp outside this window are rejected
    #: as a replay, regardless of signature validity.
    replay_window_seconds: float = Field(
        default=300.0, alias="SITE_API_REPLAY_WINDOW_SECONDS"
    )

    @classmethod
    def from_env(cls) -> Settings:
        # pydantic-settings sources required fields (instance_id, database_url)
        # from the environment at runtime; mypy cannot see that, hence the ignore.
        return cls()  # type: ignore[call-arg]
