"""Shared bounded exponential-backoff policy with optional jitter."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    base_seconds: float = 2
    maximum_seconds: float = 300
    jitter_ratio: float = 0.2

    def delay(self, attempt: int, *, random_value: float | None = None) -> float:
        raw = min(self.maximum_seconds, self.base_seconds * (2 ** max(0, attempt - 1)))
        sampled = random.random() if random_value is None else random_value
        jitter = raw * self.jitter_ratio * ((sampled * 2) - 1)
        return float(max(0, min(self.maximum_seconds, raw + jitter)))
