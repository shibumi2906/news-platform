"""Transactional outbox contract (ADR-006).

Stage 1A defines the writer interface only. Concrete outbox tables and
event payloads are owned by the domain package that produces them and are
added together with that domain's migrations (Stage 1B onward).
"""

from __future__ import annotations

from typing import Any, Protocol


class OutboxWriter(Protocol):
    """Writes a domain event to the outbox in the same DB transaction as the
    operation that produced it, guaranteeing at-least-once delivery."""

    async def write(self, event_type: str, payload: dict[str, Any]) -> None: ...
