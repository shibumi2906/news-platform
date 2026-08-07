from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field, SecretStr, model_validator


class Settings(BaseAppSettings):
    """Integrator API settings. `instance_type` defaults to `integrator` since
    this application only ever runs as part of an integrator installation."""

    instance_type: InstanceType = InstanceType.INTEGRATOR
    admin_auth_enabled: bool = Field(default=True, alias="ADMIN_AUTH_ENABLED")
    admin_api_token: SecretStr | None = Field(default=None, alias="ADMIN_API_TOKEN")
    site_api_url: str = Field(default="http://site-api:8000", alias="SITE_API_URL")
    admin_introspection_timeout_seconds: float = Field(
        default=5.0, ge=0.1, le=30.0, alias="ADMIN_INTROSPECTION_TIMEOUT_SECONDS"
    )

    @model_validator(mode="after")
    def validate_integrator_production_secrets(self) -> Settings:
        if self.app_env.lower() in {"production", "staging"} and (
            not self.admin_api_token or len(self.admin_api_token.get_secret_value()) < 32
        ):
            raise ValueError("production ADMIN_API_TOKEN must contain at least 32 characters")
        return self

    @classmethod
    def from_env(cls) -> Settings:
        # pydantic-settings sources required fields (instance_id, database_url)
        # from the environment at runtime; mypy cannot see that, hence the ignore.
        return cls()  # type: ignore[call-arg]
