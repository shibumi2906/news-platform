"""Shared configuration base.

Precedence (low to high), per docs/24_CONFIGURATION_REFERENCE.md:
field default < .env file < process environment.
Secret-manager-backed values are expected to be injected as process
environment variables, so no separate precedence tier is implemented here.
"""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class InstanceType(StrEnum):
    INTEGRATOR = "integrator"
    SITE = "site"


class BaseAppSettings(BaseSettings):
    """Settings common to every service in every installation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    instance_id: str = Field(alias="INSTANCE_ID")
    instance_type: InstanceType = Field(alias="INSTANCE_TYPE")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    timezone: str = Field(default="UTC", alias="TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    admin_auth_enabled: bool = Field(default=False, alias="ADMIN_AUTH_ENABLED")
    admin_session_keys: SecretStr = Field(
        default=SecretStr("dev-v1:change-me-session-signing-key-32-characters"),
        alias="ADMIN_SESSION_KEYS",
    )
    admin_session_ttl_seconds: int = Field(default=28_800, alias="ADMIN_SESSION_TTL_SECONDS")
    admin_session_idle_seconds: int = Field(default=3_600, alias="ADMIN_SESSION_IDLE_SECONDS")
    allowed_hosts: str = Field(
        default="localhost,127.0.0.1,testserver,test,site,integrator",
        alias="ALLOWED_HOSTS",
    )
    allowed_origins: str = Field(default="http://localhost:3000", alias="ALLOWED_ORIGINS")
    metrics_enabled: bool = Field(default=True, alias="METRICS_ENABLED")
    otel_service_name: str | None = Field(default=None, alias="OTEL_SERVICE_NAME")
    graceful_shutdown_seconds: int = Field(default=30, alias="GRACEFUL_SHUTDOWN_SECONDS")
    readiness_require_redis: bool = Field(default=False, alias="READINESS_REQUIRE_REDIS")

    @model_validator(mode="after")
    def validate_production_settings(self) -> BaseAppSettings:
        if self.app_env.lower() not in {"production", "staging"}:
            return self
        unsafe = ("change-me", "localhost")
        if any(marker in self.database_url for marker in unsafe):
            raise ValueError("production DATABASE_URL contains an unsafe placeholder")
        if self.admin_auth_enabled:
            session_keys = self.admin_session_keys.get_secret_value()
            if "change-me" in session_keys:
                raise ValueError("production ADMIN_SESSION_KEYS must be rotated")
            seen_key_ids: set[str] = set()
            for item in session_keys.split(","):
                kid, separator, secret = item.partition(":")
                if (
                    not separator
                    or not kid
                    or len(secret) < 32
                    or kid in seen_key_ids
                ):
                    raise ValueError("production ADMIN_SESSION_KEYS contains an invalid key")
                seen_key_ids.add(kid)
        hosts = [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]
        if not hosts or "*" in hosts:
            raise ValueError("production ALLOWED_HOSTS must be explicit")
        origins = [item.strip() for item in self.allowed_origins.split(",") if item.strip()]
        if not origins or any(urlparse(origin).scheme != "https" for origin in origins):
            raise ValueError("production ALLOWED_ORIGINS must contain HTTPS origins")
        redis = urlparse(self.redis_url)
        if redis.hostname in {None, "localhost", "127.0.0.1"} or not redis.password:
            raise ValueError("production REDIS_URL must be remote and authenticated")
        return self
