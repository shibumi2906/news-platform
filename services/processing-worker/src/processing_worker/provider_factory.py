from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace

from common.logging import get_logger
from common.observability import METRICS
from integrator_domain.models import AIConfigRelease, AIQualityPolicy, PromptVersion
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from processing_worker.ai_gateway import (
    AIGateway,
    AIGatewayError,
    AIProvider,
    AIRequest,
    FakeAIProvider,
    GatewayResponse,
)
from processing_worker.config import Settings
from processing_worker.openai_provider import OpenAIResponsesProvider

logger = get_logger(__name__)


def build_configured_gateway(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> AIGateway:
    fallback = [_provider(settings, name, None) for name in _provider_names(settings)]
    if session_factory is None:
        return AIGateway(
            fallback, max_attempts_per_provider=settings.ai_max_attempts_per_provider
        )
    return QualityRoutedGateway(settings, session_factory, fallback)


class QualityRoutedGateway(AIGateway):
    """Select approved per-operation releases while retaining provider fallback."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        fallback: list[AIProvider],
    ) -> None:
        super().__init__(
            fallback, max_attempts_per_provider=settings.ai_max_attempts_per_provider
        )
        self._settings = settings
        self._session_factory = session_factory
        self._fallback = fallback

    async def complete(self, request: AIRequest) -> GatewayResponse:
        async with self._session_factory() as session:
            releases = list(
                (
                    await session.execute(
                        select(AIConfigRelease).where(
                            AIConfigRelease.status.in_(["active", "canary"])
                        ).order_by(AIConfigRelease.created_at.desc())
                    )
                ).scalars()
            )
            releases = [
                item for item in releases if item.audit.get("operation") == request.operation
            ]
            policy = await session.scalar(
                select(AIQualityPolicy).where(AIQualityPolicy.operation == request.operation)
            )
            selected = _select_release(request, releases)
            if selected is None:
                if policy is not None or releases:
                    METRICS.increment("ai_routing_rejected_total", reason="no_active_release")
                    raise AIGatewayError(
                        "no_active_release", provider="routing", model="unknown"
                    )
                logger.warning("ai_runtime_legacy_route", operation=request.operation)
                return await super().complete(request)
            prompt = await session.get(PromptVersion, selected.prompt_version_id)
            if prompt is None:
                raise AIGatewayError(
                    "release_prompt_missing", provider=selected.provider, model=selected.model
                )

        keep_active_prompt = selected.audit.get("keep_active_prompt", False)
        routed_request = request if keep_active_prompt else AIRequest(
            operation=request.operation,
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            input_data=request.input_data,
        )
        primary = _provider(self._settings, selected.provider, selected.model)
        fallbacks = [
            item
            for item in self._fallback
            if (item.name, item.model) != (primary.name, primary.model)
            and (not selected.audit.get("model_only") or item.name != "fake")
        ]
        gateway = AIGateway(
            [primary, *fallbacks],
            max_attempts_per_provider=self._settings.ai_max_attempts_per_provider,
            max_cost_usd=policy.budget_usd if policy else 0.0,
        )
        logger.info(
            "ai_runtime_route_selected",
            operation=request.operation,
            release_id=str(selected.id),
            release_status=selected.status,
            provider=selected.provider,
            model=selected.model,
            budget_usd=policy.budget_usd if policy else 0.0,
        )
        METRICS.increment(
            "ai_runtime_route_total",
            operation=request.operation,
            release_status=selected.status,
            provider=selected.provider,
            model=selected.model,
        )
        try:
            response = await gateway.complete(routed_request)
        except AIGatewayError as exc:
            if exc.code == "budget_exceeded":
                METRICS.increment("ai_budget_rejection_total", operation=request.operation)
            raise
        return replace(
            response, release_id=selected.id,
            prompt_version_id=None if keep_active_prompt else selected.prompt_version_id,
        )


def _select_release(
    request: AIRequest, releases: list[AIConfigRelease]
) -> AIConfigRelease | None:
    active = next((item for item in releases if item.status == "active"), None)
    canary = next((item for item in releases if item.status == "canary"), None)
    if canary is None:
        return active
    stable = json.dumps(request.input_data, sort_keys=True, ensure_ascii=False, default=str)
    bucket = int(
        hashlib.sha256(f"{request.operation}:{stable}".encode()).hexdigest()[:8], 16
    ) % 100
    return canary if bucket < canary.rollout_percent else active


def _provider_names(settings: Settings) -> list[str]:
    return [value.strip() for value in settings.ai_providers.split(",") if value.strip()]


def _provider(settings: Settings, name: str, model: str | None) -> AIProvider:
    factories: dict[str, Callable[[], AIProvider]] = {
        "fake": lambda: FakeAIProvider(model=model or "deterministic-v1"),
        "openai": lambda: _openai_provider(settings, model),
    }
    factory = factories.get(name)
    if factory is None:
        raise ValueError(f"AI provider adapter is not installed: {name}")
    return factory()


def _openai_provider(settings: Settings, model: str | None = None) -> OpenAIResponsesProvider:
    if settings.openai_api_key is None:
        raise ValueError("OPENAI_API_KEY is required when AI_PROVIDERS includes openai")
    selected = model or settings.openai_model
    input_cost, output_cost = openai_model_rates(settings, selected)
    return OpenAIResponsesProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=selected,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
        input_cost_per_million=input_cost,
        output_cost_per_million=output_cost,
    )


OPENAI_MODEL_RATES = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-4o-mini": (0.15, 0.60),
}


def openai_model_rates(settings: Settings, model: str) -> tuple[float, float]:
    if model == settings.openai_model and (
        settings.openai_input_cost_per_million or settings.openai_output_cost_per_million
    ):
        return settings.openai_input_cost_per_million, settings.openai_output_cost_per_million
    return OPENAI_MODEL_RATES.get(model, (0.0, 0.0))
