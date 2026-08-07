"""Structured JSON logging, backed by Loguru.

docs/02_SYSTEM_ARCHITECTURE.md §12 requires structured logs and a
correlation ID that travels through every processing step. `configure_logging`
wires a single JSON-to-stdout sink and nothing else — containers must never
own log files, so no file sink is ever added here.
"""

from __future__ import annotations

import json
import re
import sys
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from loguru import logger as _loguru_logger

from common.time import to_iso8601

if TYPE_CHECKING:
    from loguru import Logger, Message

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "authorization",
        "body",
        "content",
        "cookie",
        "credential",
        "email",
        "password",
        "payload",
        "raw",
        "secret",
        "token",
    }
)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def bind_correlation_id(correlation_id: str) -> Token[str | None]:
    """Bind a trusted request/task correlation ID and return its reset token."""
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: Token[str | None]) -> None:
    _correlation_id.reset(token)


def bind_trace_id(trace_id: str) -> Token[str | None]:
    return _trace_id.set(trace_id)


def reset_trace_id(token: Token[str | None]) -> None:
    _trace_id.reset(token)


def new_correlation_id() -> str:
    return str(uuid4())


def _json_sink(message: Message) -> None:
    record = message.record
    payload: dict[str, Any] = {
        "timestamp": to_iso8601(record["time"]),
        "level": record["level"].name,
        "event": record["message"],
    }
    correlation_id = _correlation_id.get()
    if correlation_id is not None:
        payload["correlation_id"] = correlation_id
    trace_id = _trace_id.get()
    if trace_id is not None:
        payload["trace_id"] = trace_id
    payload.update(_redact(record["extra"]))
    if record["exception"] is not None:
        exception_type = record["exception"].type
        payload["exception"] = {
            "type": exception_type.__name__ if exception_type is not None else "Exception"
        }
    sys.stdout.write(json.dumps(payload, default=str) + "\n")


def _redact(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_redact(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    parts = {part for part in re.split(r"[^a-z0-9]+", key.lower()) if part}
    return bool(parts & _SENSITIVE_KEY_PARTS)


def configure_logging(log_level: str = "INFO") -> None:
    """Reset Loguru to a single JSON-to-stdout sink at the given level."""
    _loguru_logger.remove()
    _loguru_logger.add(
        _json_sink,
        level=log_level.upper(),
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )


class BoundLogger:
    """Adapter exposing `logger.info(event, **fields)` calls over Loguru."""

    __slots__ = ("_logger",)

    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    def _emit(self, level: str, event: str, **fields: Any) -> None:
        bound = self._logger.bind(**fields) if fields else self._logger
        getattr(bound, level)(event)

    def debug(self, event: str, **fields: Any) -> None:
        self._emit("debug", event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit("info", event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit("warning", event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit("error", event, **fields)

    def critical(self, event: str, **fields: Any) -> None:
        self._emit("critical", event, **fields)

    def exception(self, event: str, **fields: Any) -> None:
        self._emit("exception", event, **fields)


def get_logger(name: str | None = None) -> BoundLogger:
    logger = _loguru_logger.bind(logger=name) if name else _loguru_logger
    return BoundLogger(logger)
