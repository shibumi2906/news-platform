"""Provider-neutral media AI gateway and deterministic fake provider."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class MediaProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class MediaModerationError(MediaProviderError):
    def __init__(self) -> None:
        super().__init__("media_prompt_rejected", retryable=False)


@dataclass(frozen=True)
class GeneratedMedia:
    data: bytes
    mime_type: str
    width: int
    height: int


@dataclass(frozen=True)
class MediaProviderResult:
    items: list[GeneratedMedia]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    latency_ms: int
    moderation: dict[str, object]


class ImageGenerationProvider(Protocol):
    name: str

    async def generate(self, prompt: str, variants: int) -> MediaProviderResult: ...


class VideoGenerationProvider(Protocol):
    """Foundation contract; production rendering is intentionally out of scope."""

    name: str

    async def render(self, script: str, scenes: list[dict[str, object]]) -> GeneratedMedia: ...


class FakeImageProvider:
    name = "fake"

    def __init__(self, *, fail_times: int = 0, moderated: bool = False) -> None:
        self.fail_times = fail_times
        self.moderated = moderated
        self.calls = 0

    async def generate(self, prompt: str, variants: int) -> MediaProviderResult:
        started = time.perf_counter()
        self.calls += 1
        if self.calls <= self.fail_times:
            raise MediaProviderError("fake_transient_error", retryable=True)
        if self.moderated:
            raise MediaModerationError()
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        hue = int(digest[:2], 16)
        items = [
            GeneratedMedia(
                data=(
                    "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='630'>"
                    f"<rect width='1200' height='630' fill='hsl({hue + index},55%,32%)'/>"
                    "<text x='60' y='570' fill='white' font-size='36'>"
                    f"AI variant {index + 1}</text>"
                    "</svg>"
                ).encode(),
                mime_type="image/svg+xml",
                width=1200,
                height=630,
            )
            for index in range(variants)
        ]
        return MediaProviderResult(
            items=items,
            provider=self.name,
            model="fake-image-v1",
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=0,
            estimated_cost_usd=Decimal("0"),
            latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
            moderation={"status": "passed"},
        )


class MediaGateway:
    def __init__(
        self, providers: list[ImageGenerationProvider], *, attempts_per_provider: int = 2
    ) -> None:
        if not providers:
            raise ValueError("at least one media provider is required")
        self.providers = providers
        self.attempts_per_provider = attempts_per_provider

    async def generate(self, prompt: str, variants: int) -> MediaProviderResult:
        last_error: MediaProviderError | None = None
        for provider in self.providers:
            for attempt in range(self.attempts_per_provider):
                try:
                    return await provider.generate(prompt, variants)
                except MediaProviderError as exc:
                    last_error = exc
                    if not exc.retryable:
                        break
                    await asyncio.sleep(0 if attempt + 1 == self.attempts_per_provider else 0.01)
        if last_error is None:
            raise MediaProviderError("provider_unavailable", retryable=True)
        raise last_error
