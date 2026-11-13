"""Site Ingestion API endpoint (docs/02 §6.4, docs/02 §9: `/api/v1/incoming-news-packages`)."""

from __future__ import annotations

from uuid import UUID

from common.auth import AuthContext, require_permission
from common.signing import (
    CONNECTION_ID_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    NONCE_HEADER,
    SIGNATURE_HEADER,
    SIGNATURE_VERSION_HEADER,
    SIGNING_KEY_ID_HEADER,
    TIMESTAMP_HEADER,
)
from contracts.ingestion import IncomingPackageReceipt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from site_domain.models import IntegratorConnection

from site_api.errors import InvalidConnectionIdError
from site_api.ingestion import ingest_package

router = APIRouter(prefix="/api/v1", tags=["ingestion"])
JobsManager = Depends(require_permission("jobs:manage"))


class SigningKeyInput(BaseModel):
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    secret: str = Field(min_length=16, max_length=255)


def _rate_limit(request: Request, actor: str) -> None:
    if not request.app.state.integration_limiter.allow(actor):
        raise HTTPException(429, "integration operation rate limit exceeded")


@router.post("/incoming-news-packages", response_model=IncomingPackageReceipt)
async def receive_incoming_package(
    request: Request,
    response: Response,
    x_connection_id: str = Header(alias=CONNECTION_ID_HEADER),
    x_signature: str = Header(alias=SIGNATURE_HEADER),
    x_signature_version: str = Header(alias=SIGNATURE_VERSION_HEADER),
    x_signing_key_id: str = Header(default="legacy", alias=SIGNING_KEY_ID_HEADER),
    x_timestamp: str = Header(alias=TIMESTAMP_HEADER),
    x_nonce: str = Header(alias=NONCE_HEADER),
    idempotency_key: str = Header(alias=IDEMPOTENCY_KEY_HEADER),
) -> IncomingPackageReceipt:
    try:
        connection_id = UUID(x_connection_id)
    except ValueError as exc:
        raise InvalidConnectionIdError(f"malformed {CONNECTION_ID_HEADER} header") from exc

    body = await request.body()

    async with request.app.state.session_factory() as session:
        receipt, status_code = await ingest_package(
            session,
            connection_id=connection_id,
            signature=x_signature,
            timestamp=x_timestamp,
            nonce=x_nonce,
            signature_version=x_signature_version,
            signing_key_id=x_signing_key_id,
            idempotency_key=idempotency_key,
            body=body,
            replay_window_seconds=request.app.state.settings.replay_window_seconds,
        )

    response.status_code = status_code
    return receipt


@router.put(
    "/admin/integrator-connections/{connection_id}/signing-key",
)
async def rotate_integrator_signing_key(
    connection_id: UUID,
    payload: SigningKeyInput,
    request: Request,
    context: AuthContext = JobsManager,
) -> dict[str, str | None]:
    _rate_limit(request, context.actor)
    async with request.app.state.session_factory() as session, session.begin():
        connection = await session.get(IntegratorConnection, connection_id)
        if connection is None:
            raise HTTPException(404, "integrator connection not found")
        if payload.key_id == connection.active_key_id:
            raise HTTPException(409, "key identifier is already active")
        connection.previous_key_id = connection.active_key_id
        connection.previous_hmac_secret = connection.hmac_secret
        connection.active_key_id = payload.key_id
        connection.hmac_secret = payload.secret
    return {
        "connection_id": str(connection.id),
        "active_key_id": connection.active_key_id,
        "previous_key_id": connection.previous_key_id,
    }


@router.delete(
    "/admin/integrator-connections/{connection_id}/previous-signing-key",
    status_code=204,
)
async def retire_integrator_signing_key(
    connection_id: UUID,
    request: Request,
    context: AuthContext = JobsManager,
) -> Response:
    _rate_limit(request, context.actor)
    async with request.app.state.session_factory() as session, session.begin():
        connection = await session.get(IntegratorConnection, connection_id)
        if connection is None:
            raise HTTPException(404, "integrator connection not found")
        connection.previous_key_id = None
        connection.previous_hmac_secret = None
    return Response(status_code=204)
