"""Site Ingestion API endpoint (docs/02 §6.4, docs/02 §9: `/api/v1/incoming-news-packages`)."""

from __future__ import annotations

from uuid import UUID

from common.signing import (
    CONNECTION_ID_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    NONCE_HEADER,
    SIGNATURE_HEADER,
    SIGNATURE_VERSION_HEADER,
    TIMESTAMP_HEADER,
)
from contracts.ingestion import IncomingPackageReceipt
from fastapi import APIRouter, Header, Request, Response

from site_api.errors import InvalidConnectionIdError
from site_api.ingestion import ingest_package

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


@router.post("/incoming-news-packages", response_model=IncomingPackageReceipt)
async def receive_incoming_package(
    request: Request,
    response: Response,
    x_connection_id: str = Header(alias=CONNECTION_ID_HEADER),
    x_signature: str = Header(alias=SIGNATURE_HEADER),
    x_signature_version: str = Header(alias=SIGNATURE_VERSION_HEADER),
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
            idempotency_key=idempotency_key,
            body=body,
            replay_window_seconds=request.app.state.settings.replay_window_seconds,
        )

    response.status_code = status_code
    return receipt
