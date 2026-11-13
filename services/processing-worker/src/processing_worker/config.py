from __future__ import annotations

from common.config import BaseAppSettings, InstanceType
from pydantic import Field, SecretStr, model_validator


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
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-6-luna", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_timeout_seconds: float = Field(default=30.0, alias="OPENAI_TIMEOUT_SECONDS")
    openai_input_cost_per_million: float = Field(default=0.0, alias="OPENAI_INPUT_COST_PER_MILLION")
    openai_output_cost_per_million: float = Field(
        default=0.0, alias="OPENAI_OUTPUT_COST_PER_MILLION"
    )

    @model_validator(mode="after")
    def validate_production_ai(self) -> Settings:
        providers = {item.strip() for item in self.ai_providers.split(",") if item.strip()}
        if self.app_env.lower() in {"production", "staging"}:
            if not providers or providers == {"fake"}:
                raise ValueError("production AI_PROVIDERS must name a configured non-fake provider")
            if "openai" in providers and self.openai_api_key is None:
                raise ValueError(
                    "OPENAI_API_KEY is required when production AI_PROVIDERS includes openai"
                )
        return self

    @classmethod
    def from_env(cls) -> Settings:
        # pydantic-settings sources required fields (instance_id, database_url)
        # from the environment at runtime; mypy cannot see that, hence the ignore.
        return cls()  # type: ignore[call-arg]
