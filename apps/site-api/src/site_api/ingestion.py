"""Site Ingestion API service logic (docs/02 §6.4, docs/14 §2, §5).

A request is verified in this order: connection lookup, replay window,
HMAC signature, then idempotency. `idempotency_key` is deterministic
(`{package_id}:{package_version}`, set by delivery-worker), so nonce/replay
window are defense-in-depth on top of idempotency rather than a separate
uniqueness mechanism (docs/14 §5: "nonce/replay window не заменяют
idempotency") — a replayed request within the window is caught by the
idempotency check below and simply returns the stored result.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal
from uuid import UUID

from common.signing import SIGNATURE_VERSION, verify
from common.time import utc_now
from contracts.ingestion import IncomingPackageReceipt
from contracts.package import CanonicalNewsPackageEnvelope
from pydantic import ValidationError
from site_domain.models import (
    IncomingPackage,
    IncomingPackageVersion,
    IngestionAttempt,
    IntegratorConnection,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from site_api.errors import (
    ConnectionNotFoundError,
    IdempotencyConflictError,
    InvalidSignatureError,
    PayloadValidationError,
    ReplayNonceError,
    ReplayWindowExceededError,
    UnsupportedSchemaVersionError,
    UnsupportedSignatureVersionError,
)

_ACCEPTED_STATUS_CODE = 201
_DUPLICATE_STATUS_CODE = 200


async def ingest_package(
    session: AsyncSession,
    *,
    connection_id: UUID,
    signature: str,
    timestamp: str,
    nonce: str,
    idempotency_key: str,
    body: bytes,
    replay_window_seconds: float,
    signature_version: str = SIGNATURE_VERSION,
) -> tuple[IncomingPackageReceipt, int]:
    connection = await session.get(IntegratorConnection, connection_id)
    if connection is None or not connection.is_active:
        raise ConnectionNotFoundError("unknown or inactive connection")

    if signature_version != SIGNATURE_VERSION:
        raise UnsupportedSignatureVersionError("unsupported signature version")

    _check_replay_window(timestamp, replay_window_seconds)

    if not verify(
        connection.hmac_secret,
        timestamp=timestamp,
        nonce=nonce,
        idempotency_key=idempotency_key,
        body=body,
        signature=signature,
    ):
        raise InvalidSignatureError("signature does not match")

    request_body_hash = hashlib.sha256(body).hexdigest()

    existing_attempt = await _find_attempt(session, connection_id, idempotency_key)
    if existing_attempt is not None:
        return _replay_stored_attempt(existing_attempt, request_body_hash)

    if await _nonce_exists(session, connection_id, nonce):
        raise ReplayNonceError("nonce has already been used")

    try:
        envelope = CanonicalNewsPackageEnvelope.model_validate_json(body)
    except ValidationError as exc:
        raise PayloadValidationError(
            "invalid canonical news package envelope",
            details={"errors": _summarize_validation_errors(exc)},
        ) from exc

    if envelope.schema_version.split(".", 1)[0] != "1":
        raise UnsupportedSchemaVersionError("unsupported canonical package schema version")

    status = await _upsert_incoming_package(session, connection_id=connection_id, envelope=envelope)
    receipt = IncomingPackageReceipt(
        package_id=envelope.package_id,
        package_version=envelope.package_version,
        status=status,
        received_at=utc_now(),
    )
    session.add(
        IngestionAttempt(
            connection_id=connection_id,
            idempotency_key=idempotency_key,
            nonce=nonce,
            request_body_hash=request_body_hash,
            package_id=envelope.package_id,
            package_version=envelope.package_version,
            status=status,
            response_body=receipt.model_dump(mode="json"),
        )
    )

    try:
        await session.commit()
    except IntegrityError:
        # A concurrent request raced us for the same (connection_id,
        # idempotency_key); the other request's attempt row now exists.
        await session.rollback()
        existing_attempt = await _find_attempt(session, connection_id, idempotency_key)
        if existing_attempt is None:
            raise
        return _replay_stored_attempt(existing_attempt, request_body_hash)

    status_code = _ACCEPTED_STATUS_CODE if status == "accepted" else _DUPLICATE_STATUS_CODE
    return receipt, status_code


def _replay_stored_attempt(
    attempt: IngestionAttempt, request_body_hash: str
) -> tuple[IncomingPackageReceipt, int]:
    if attempt.request_body_hash != request_body_hash:
        raise IdempotencyConflictError("idempotency key already used with a different request body")
    receipt = IncomingPackageReceipt.model_validate(attempt.response_body)
    status_code = _ACCEPTED_STATUS_CODE if receipt.status == "accepted" else _DUPLICATE_STATUS_CODE
    return receipt, status_code


async def _find_attempt(
    session: AsyncSession, connection_id: UUID, idempotency_key: str
) -> IngestionAttempt | None:
    result = await session.execute(
        select(IngestionAttempt).where(
            IngestionAttempt.connection_id == connection_id,
            IngestionAttempt.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def _nonce_exists(session: AsyncSession, connection_id: UUID, nonce: str) -> bool:
    result = await session.execute(
        select(IngestionAttempt.id).where(
            IngestionAttempt.connection_id == connection_id,
            IngestionAttempt.nonce == nonce,
        )
    )
    return result.first() is not None


def _check_replay_window(timestamp: str, replay_window_seconds: float) -> None:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayWindowExceededError("malformed timestamp") from exc
    if parsed.tzinfo is None:
        raise ReplayWindowExceededError("timestamp must include a timezone")
    delta = abs((utc_now() - parsed).total_seconds())
    if delta > replay_window_seconds:
        raise ReplayWindowExceededError("timestamp outside the accepted replay window")


async def _upsert_incoming_package(
    session: AsyncSession, *, connection_id: UUID, envelope: CanonicalNewsPackageEnvelope
) -> Literal["accepted", "duplicate"]:
    result = await session.execute(
        select(IncomingPackage).where(
            IncomingPackage.connection_id == connection_id,
            IncomingPackage.package_id == envelope.package_id,
        )
    )
    incoming_package = result.scalar_one_or_none()

    if incoming_package is None:
        incoming_package = IncomingPackage(
            connection_id=connection_id,
            package_id=envelope.package_id,
            latest_version=envelope.package_version,
        )
        session.add(incoming_package)
        await session.flush()
    else:
        version_result = await session.execute(
            select(IncomingPackageVersion).where(
                IncomingPackageVersion.incoming_package_id == incoming_package.id,
                IncomingPackageVersion.package_version == envelope.package_version,
            )
        )
        if version_result.scalar_one_or_none() is not None:
            return "duplicate"
        # Deliveries are not guaranteed to arrive in order; never regress.
        incoming_package.latest_version = max(
            incoming_package.latest_version, envelope.package_version
        )

    session.add(
        IncomingPackageVersion(
            incoming_package_id=incoming_package.id,
            package_version=envelope.package_version,
            payload=envelope.model_dump(mode="json"),
        )
    )
    return "accepted"


def _summarize_validation_errors(exc: ValidationError) -> list[dict[str, object]]:
    return [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
