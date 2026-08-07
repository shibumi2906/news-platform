"""Provider-neutral AI gateway with bounded retries and fallback routing."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from common.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class AIRequest:
    operation: str
    system_prompt: str
    user_prompt: str
    input_data: dict[str, Any]


@dataclass(frozen=True)
class ProviderResponse:
    output: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class GatewayResponse:
    provider: str
    model: str
    output: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    attempts: int


class AIProvider(Protocol):
    name: str
    model: str

    async def complete(self, request: AIRequest) -> ProviderResponse: ...


class AIProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class AIGatewayError(RuntimeError):
    def __init__(self, code: str, *, provider: str, model: str) -> None:
        super().__init__(code)
        self.code = code
        self.provider = provider
        self.model = model


class AIGateway:
    def __init__(
        self,
        providers: list[AIProvider],
        *,
        max_attempts_per_provider: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not providers:
            raise ValueError("at least one AI provider is required")
        self._providers = providers
        self._max_attempts = max_attempts_per_provider
        self._sleep = sleep

    async def complete(self, request: AIRequest) -> GatewayResponse:
        started = perf_counter()
        attempts = 0
        last_code = "provider_unavailable"
        last_provider = "routing"
        last_model = "unknown"
        for provider in self._providers:
            last_provider, last_model = provider.name, provider.model
            for attempt in range(1, self._max_attempts + 1):
                attempts += 1
                try:
                    result = await provider.complete(request)
                    latency_ms = round((perf_counter() - started) * 1000)
                    logger.info(
                        "ai_call_completed",
                        operation=request.operation,
                        provider=provider.name,
                        model=provider.model,
                        attempts=attempts,
                        latency_ms=latency_ms,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        estimated_cost_usd=result.estimated_cost_usd,
                    )
                    return GatewayResponse(
                        provider=provider.name,
                        model=provider.model,
                        output=result.output,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        estimated_cost_usd=result.estimated_cost_usd,
                        latency_ms=latency_ms,
                        attempts=attempts,
                    )
                except AIProviderError as exc:
                    last_code = exc.code
                    logger.warning(
                        "ai_call_failed",
                        operation=request.operation,
                        provider=provider.name,
                        model=provider.model,
                        attempt=attempt,
                        error_code=exc.code,
                    )
                    if not exc.retryable or attempt == self._max_attempts:
                        break
                    await self._sleep(float(2 ** (attempt - 1)))
        raise AIGatewayError(last_code, provider=last_provider, model=last_model)


class FakeAIProvider:
    """Deterministic, offline provider used by tests and local development."""

    name = "fake"
    model = "deterministic-v1"

    def __init__(
        self,
        responses: Mapping[str, dict[str, Any]] | None = None,
        *,
        failures: Mapping[str, int] | None = None,
    ) -> None:
        self._responses = dict(responses or {})
        self._failures = dict(failures or {})

    async def complete(self, request: AIRequest) -> ProviderResponse:
        remaining = self._failures.get(request.operation, 0)
        if remaining:
            self._failures[request.operation] = remaining - 1
            raise AIProviderError("fake_transient_error")
        output = self._responses.get(request.operation)
        if output is None:
            output = self._generate(request)
        prompt_tokens = max(1, (len(request.system_prompt) + len(request.user_prompt)) // 4)
        completion_tokens = max(1, len(str(output)) // 4)
        return ProviderResponse(
            output=output,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _generate(self, request: AIRequest) -> dict[str, Any]:
        if request.operation == "relevance":
            return _fake_relevance(request.input_data)
        if request.operation == "extraction":
            return _fake_extraction(request.input_data)
        if request.operation == "draft":
            return _fake_draft(request.input_data)
        if request.operation == "language_detection":
            return {
                "language_code": request.input_data.get("declared_language") or "en",
                "confidence": 0.99,
            }
        if request.operation == "translation":
            return _fake_translation(request.input_data)
        raise AIProviderError("unsupported_operation", retryable=False)


def build_gateway(provider_names: str, *, max_attempts_per_provider: int) -> AIGateway:
    """Resolve configured provider adapters without exposing them to domain operations."""
    factories: dict[str, Callable[[], AIProvider]] = {"fake": FakeAIProvider}
    providers: list[AIProvider] = []
    for name in (value.strip() for value in provider_names.split(",")):
        factory = factories.get(name)
        if factory is None:
            raise ValueError(f"AI provider adapter is not installed: {name}")
        providers.append(factory())
    return AIGateway(providers, max_attempts_per_provider=max_attempts_per_provider)


def _fake_relevance(data: dict[str, Any]) -> dict[str, Any]:
    text = str(data.get("text", "")).casefold()
    matches: list[dict[str, Any]] = []
    for topic in data.get("topics", []):
        keywords = [str(value).casefold() for value in topic.get("keywords", [])]
        exclusions = [str(value).casefold() for value in topic.get("exclusions", [])]
        regions = [str(value).casefold() for value in topic.get("regions", [])]
        matched_keywords = [value for value in keywords if value and value in text]
        excluded = [value for value in exclusions if value and value in text]
        region_match = not regions or any(value in text for value in regions)
        rules = topic.get("additional_rules", {})
        required = [str(value).casefold() for value in rules.get("required_terms", [])]
        required_match = all(value in text for value in required)
        minimum = int(rules.get("minimum_keyword_matches", 1))
        score = min(1.0, 0.5 + 0.15 * len(matched_keywords))
        relevant = (
            len(matched_keywords) >= minimum
            and not excluded
            and region_match
            and required_match
            and score >= float(topic.get("relevance_threshold", 0.5))
        )
        categories = topic.get("categories", [])
        category_slug = None
        for category in categories:
            category_keywords = [str(value).casefold() for value in category.get("keywords", [])]
            if not category_keywords or any(value in text for value in category_keywords):
                category_slug = category.get("slug")
                break
        matches.append(
            {
                "topic_id": topic["id"],
                "category_slug": category_slug,
                "score": score if relevant else 0.0,
                "is_relevant": relevant,
                "reason": {
                    "matched_keywords": matched_keywords,
                    "excluded_terms": excluded,
                    "region_match": region_match,
                    "required_terms_match": required_match,
                },
            }
        )
    return {"matches": matches}


def _fake_extraction(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title", ""))
    body = str(data.get("body", ""))
    names = list(dict.fromkeys(re.findall(r"\b[A-Z][\w.-]*(?:\s+[A-Z][\w.-]*)*", title)))
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", f"{title} {body}")
    entities = [{"kind": "organization", "name": name, "confidence": 0.8} for name in names] + [
        {"kind": "date", "name": value, "confidence": 1.0} for value in dates
    ]
    event_key_terms = sorted({name.casefold() for name in names}) or [title.casefold()[:80]]
    return {
        "facts": [
            {
                "statement": title,
                "fact_type": "reported_claim",
                "value": {"text": title},
                "confidence": 0.8,
            }
        ],
        "entities": entities,
        "dates": dates,
        "tags": names,
        "event_key": "|".join(event_key_terms),
    }


def _fake_draft(data: dict[str, Any]) -> dict[str, Any]:
    materials = data.get("materials", [])
    first = materials[0]
    body_parts = [str(item.get("body") or item.get("excerpt") or "") for item in materials]
    body = "\n\n".join(part for part in body_parts if part)
    return {
        "title": first["title"],
        "lead": str(first.get("excerpt") or body[:240]),
        "body": body,
        "summary": body[:500],
        "tags": data.get("tags", []),
    }


def _fake_translation(data: dict[str, Any]) -> dict[str, Any]:
    content = dict(data["content"])
    for entry in data.get("terminology", []):
        source = str(entry["source_term"])
        target = str(entry["target_term"])
        for field in ("title", "lead", "body", "summary"):
            content[field] = str(content[field]).replace(source, target)
        content["tags"] = [str(tag).replace(source, target) for tag in content.get("tags", [])]
    prefix = f"[{data['target_language']}] "
    return {
        "title": prefix + str(content["title"]),
        "lead": prefix + str(content["lead"]),
        "body": prefix + str(content["body"]),
        "summary": prefix + str(content["summary"]),
        "tags": list(content.get("tags", [])),
    }
