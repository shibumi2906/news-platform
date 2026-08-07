"""Small dependency-free metrics and W3C trace-context foundation."""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from time import monotonic
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)

    def increment(self, name: str, value: float = 1, **labels: str) -> None:
        with self._lock:
            self._counters[(name, tuple(sorted(labels.items())))] += value

    def gauge(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._gauges[(name, tuple(sorted(labels.items())))] = value

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            values = [*self._counters.items(), *self._gauges.items()]
        for (name, labels), value in sorted(values):
            suffix = ""
            if labels:
                encoded = ",".join(f'{key}="{_escape(label)}"' for key, label in labels)
                suffix = "{" + encoded + "}"
            lines.append(f"{name}{suffix} {value:g}")
        return "\n".join(lines) + "\n"


METRICS = MetricsRegistry()
router = APIRouter(tags=["observability"])


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def metrics(request: Request) -> str:
    if not request.app.state.settings.metrics_enabled:
        return "# metrics disabled\n"
    return METRICS.render()


def trace_context(value: str | None) -> tuple[str, str]:
    match = _TRACEPARENT.fullmatch(value or "")
    trace_id = match.group(1) if match and match.group(1) != "0" * 32 else uuid4().hex
    span_id = uuid4().hex[:16]
    return trace_id, f"00-{trace_id}-{span_id}-01"


def request_started() -> float:
    METRICS.gauge("http_requests_in_flight", 1)
    return monotonic()


def request_finished(started: float, method: str, route: str, status_code: int) -> None:
    METRICS.gauge("http_requests_in_flight", 0)
    METRICS.increment(
        "http_requests_total",
        method=method,
        route=route,
        status_class=f"{status_code // 100}xx",
    )
    METRICS.increment(
        "http_request_duration_seconds_sum",
        monotonic() - started,
        method=method,
        route=route,
    )


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
