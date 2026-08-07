from __future__ import annotations

from collections.abc import Callable

from processing_worker.ai_gateway import AIGateway, AIProvider, FakeAIProvider
from processing_worker.config import Settings
from processing_worker.openai_provider import OpenAIResponsesProvider


def build_configured_gateway(settings: Settings) -> AIGateway:
    factories: dict[str, Callable[[], AIProvider]] = {
        "fake": FakeAIProvider,
        "openai": lambda: _openai_provider(settings),
    }
    providers: list[AIProvider] = []
    for name in (value.strip() for value in settings.ai_providers.split(",")):
        factory = factories.get(name)
        if factory is None:
            raise ValueError(f"AI provider adapter is not installed: {name}")
        providers.append(factory())
    return AIGateway(
        providers, max_attempts_per_provider=settings.ai_max_attempts_per_provider
    )


def _openai_provider(settings: Settings) -> OpenAIResponsesProvider:
    if settings.openai_api_key is None:
        raise ValueError("OPENAI_API_KEY is required when AI_PROVIDERS includes openai")
    return OpenAIResponsesProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
        input_cost_per_million=settings.openai_input_cost_per_million,
        output_cost_per_million=settings.openai_output_cost_per_million,
    )
