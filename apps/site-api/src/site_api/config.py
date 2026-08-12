from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field, SecretStr, model_validator


class Settings(BaseAppSettings):
    """Site API settings. `instance_type` defaults to `site` since
    this application only ever runs as part of a site installation."""

    instance_type: InstanceType = InstanceType.SITE
    admin_auth_enabled: bool = Field(default=True, alias="ADMIN_AUTH_ENABLED")

    #: docs/14 §2: requests with a timestamp outside this window are rejected
    #: as a replay, regardless of signature validity.
    replay_window_seconds: float = Field(default=300.0, alias="SITE_API_REPLAY_WINDOW_SECONDS")
    admin_api_token: SecretStr | None = Field(default=None, alias="ADMIN_API_TOKEN")
    s3_endpoint_url: str = Field(default="http://minio:9000", alias="S3_ENDPOINT_URL")
    s3_access_key: SecretStr = Field(default=SecretStr("change-me"), alias="S3_ACCESS_KEY")
    s3_secret_key: SecretStr = Field(default=SecretStr("change-me"), alias="S3_SECRET_KEY")
    s3_bucket: str = Field(default="site-media", alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    media_upload_max_bytes: int = Field(default=10_485_760, alias="MEDIA_UPLOAD_MAX_BYTES")
    media_attempts_per_provider: int = Field(default=2, alias="MEDIA_ATTEMPTS_PER_PROVIDER")
    admin_bootstrap_username: str | None = Field(default=None, alias="ADMIN_BOOTSTRAP_USERNAME")
    admin_bootstrap_password: SecretStr | None = Field(
        default=None, alias="ADMIN_BOOTSTRAP_PASSWORD"
    )
    auth_login_attempts_per_minute: int = Field(default=10, alias="AUTH_LOGIN_ATTEMPTS_PER_MINUTE")
    dashboard_url: str | None = Field(default=None, alias="SUPABASE_DASHBOARD_URL")
    dashboard_key: SecretStr | None = Field(default=None, alias="SUPABASE_DASHBOARD_KEY")
    dashboard_retry_base_seconds: int = Field(default=30, alias="DASHBOARD_RETRY_BASE_SECONDS")

    @model_validator(mode="after")
    def validate_site_production_secrets(self) -> Settings:
        if bool(self.dashboard_url) != bool(self.dashboard_key):
            raise ValueError(
                "SUPABASE_DASHBOARD_URL and SUPABASE_DASHBOARD_KEY must be set together"
            )
        if self.app_env.lower() not in {"production", "staging"}:
            return self
        secrets = [self.s3_access_key.get_secret_value(), self.s3_secret_key.get_secret_value()]
        if any("change-me" in value or len(value) < 12 for value in secrets):
            raise ValueError("production object-storage credentials are unsafe")
        if not self.admin_api_token or len(self.admin_api_token.get_secret_value()) < 32:
            raise ValueError("production ADMIN_API_TOKEN must contain at least 32 characters")
        bootstrap_password = (
            self.admin_bootstrap_password.get_secret_value()
            if self.admin_bootstrap_password
            else ""
        )
        if bool(self.admin_bootstrap_username) != bool(bootstrap_password):
            raise ValueError("production bootstrap username and password must be set together")
        if bootstrap_password and len(bootstrap_password) < 12:
            raise ValueError("production bootstrap password must contain at least 12 characters")
        return self

    @classmethod
    def from_env(cls) -> Settings:
        # pydantic-settings sources required fields (instance_id, database_url)
        # from the environment at runtime; mypy cannot see that, hence the ignore.
        return cls()  # type: ignore[call-arg]
