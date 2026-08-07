from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field, SecretStr


class Settings(BaseAppSettings):
    """Integrator API settings. `instance_type` defaults to `integrator` since
    this application only ever runs as part of an integrator installation."""

    instance_type: InstanceType = InstanceType.INTEGRATOR
    admin_api_token: SecretStr | None = Field(default=None, alias="ADMIN_API_TOKEN")

    @classmethod
    def from_env(cls) -> Settings:
        # pydantic-settings sources required fields (instance_id, database_url)
        # from the environment at runtime; mypy cannot see that, hence the ignore.
        return cls()  # type: ignore[call-arg]
