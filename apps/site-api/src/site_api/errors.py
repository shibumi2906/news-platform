"""Site Ingestion API error taxonomy (docs/14_PUBLIC_AND_INTERNAL_API.md §2, §5).

Each subclass is caught by the `DomainError` handler in `site_api.main` and
rendered as the shared `ErrorEnvelope` shape.
"""

from __future__ import annotations

from common.errors import DomainError


class InvalidConnectionIdError(DomainError):
    code = "invalid_connection_id"
    status_code = 400


class ConnectionNotFoundError(DomainError):
    code = "connection_not_found"
    status_code = 404


class ReplayWindowExceededError(DomainError):
    code = "replay_window_exceeded"
    status_code = 401


class InvalidSignatureError(DomainError):
    code = "invalid_signature"
    status_code = 401


class UnsupportedSignatureVersionError(DomainError):
    code = "unsupported_signature_version"
    status_code = 401


class UnknownSigningKeyError(DomainError):
    code = "unknown_signing_key"
    status_code = 401


class ReplayNonceError(DomainError):
    code = "replay_nonce"
    status_code = 401


class UnsupportedSchemaVersionError(DomainError):
    code = "unsupported_schema_version"
    status_code = 422


class IdempotencyConflictError(DomainError):
    code = "idempotency_conflict"
    status_code = 409


class PayloadValidationError(DomainError):
    code = "validation_error"
    status_code = 422


class NotFoundError(DomainError):
    code = "not_found"
    status_code = 404


class ConflictError(DomainError):
    code = "conflict"
    status_code = 409


class ValidationDomainError(DomainError):
    code = "validation_error"
    status_code = 422
