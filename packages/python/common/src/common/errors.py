"""Shared error envelope.

Matches the API-wide error contract from docs/14_PUBLIC_AND_INTERNAL_API.md
§1: `{"error": {"code", "message", "details", "correlation_id"}}`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    correlation_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class DomainError(Exception):
    """Base class for errors that must be surfaced as a structured ErrorEnvelope."""

    code: str = "internal_error"
    status_code: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
