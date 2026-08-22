"""Shared configuration base.

Precedence (low to high), per docs/24_CONFIGURATION_REFERENCE.md:
field default < .env file < process environment.
Secret-manager-backed values are expected to be injected as process
environment variables, so no separate precedence tier is implemented here.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
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
