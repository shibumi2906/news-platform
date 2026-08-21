"""Provider capabilities shared by scheduling and distribution workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ContentType = Literal["text", "link", "image", "video"]


@dataclass(frozen=True)
class ProviderCapabilities:
    content_types: frozenset[ContentType]
    text_limit: int
    requires_media_url: bool = False


PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "telegram": ProviderCapabilities(frozenset({"text", "link", "image", "video"}), 4096),
    "facebook": ProviderCapabilities(frozenset({"text", "link", "image", "video"}), 63_206),
    "instagram": ProviderCapabilities(frozenset({"image", "video"}), 2_200, True),
    "tiktok": ProviderCapabilities(frozenset({"video"}), 2_200, True),
    "x": ProviderCapabilities(frozenset({"text", "link"}), 280),
    "youtube": ProviderCapabilities(frozenset({"video"}), 5_000, True),
}


def capabilities_for(kind: str) -> ProviderCapabilities:
    try:
        return PROVIDER_CAPABILITIES[kind]
    except KeyError as exc:
        raise ValueError("unsupported distribution channel kind") from exc
