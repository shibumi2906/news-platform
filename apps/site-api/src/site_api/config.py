from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field, SecretStr


class Settings(BaseAppSettings):
    """Site API settings. `instance_type` defaults to `site` since
    this application only ever runs as part of a site installation."""

    instance_type: InstanceType = InstanceType.SITE

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

    @classmethod
    def from_env(cls) -> Settings:
        # pydantic-settings sources required fields (instance_id, database_url)
        # from the environment at runtime; mypy cannot see that, hence the ignore.
        return cls()  # type: ignore[call-arg]
