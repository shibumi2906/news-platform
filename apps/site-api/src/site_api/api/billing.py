from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common.auth import require_permission
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from site_api.billing import BillingError, BillingRepository, BillingService

router = APIRouter(
    prefix="/api/v1/admin/billing",
    tags=["billing"],
    dependencies=[Depends(require_permission("billing:manage"))],
)
webhook_router = APIRouter(prefix="/webhooks/payments", tags=["billing"])


class CustomerIn(BaseModel):
    email: str | None = Field(default=None, max_length=320)
    attributes: dict[str, Any] = Field(default_factory=dict)


class InvoiceIn(BaseModel):
    customer_id: uuid.UUID
    amount_minor: int
    currency: str = Field(min_length=3, max_length=3)
    idempotency_key: str = Field(min_length=1, max_length=255)


class PaymentIn(BaseModel):
    provider: str = Field(pattern=r"^[a-z0-9_-]{2,64}$")


def service(request: Request, session: Any) -> BillingService:
    return BillingService(
        BillingRepository(session, request.app.state.settings.instance_id),
        getattr(request.app.state, "payment_providers", {}),
    )


def out(x: Any) -> dict[str, Any]:
    return {
        "id": str(x.id),
        "status": x.status,
        "amount_minor": getattr(x, "amount_minor", None),
        "currency": getattr(x, "currency", None),
    }


async def run(request: Request, action: Any) -> Any:
    async with request.app.state.session_factory() as session:
        try:
            result = await action(service(request, session))
            await session.commit()
            return result
        except BillingError:
            await session.rollback()
            raise


@router.post("/customers", status_code=201)
async def customer(payload: CustomerIn, request: Request) -> dict[str, Any]:
    x = await run(request, lambda s: s.create_customer(payload.email, payload.attributes))
    return out(x)


@router.get("/invoices", response_model=list[dict[str, Any]])
async def invoices(request: Request) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        return [out(row) for row in await service(request, session).repo.invoices()]


@router.post("/invoices", status_code=201)
async def invoice(payload: InvoiceIn, request: Request) -> dict[str, Any]:
    x, _ = await run(
        request,
        lambda s: s.create_invoice(
            payload.customer_id, payload.amount_minor, payload.currency, payload.idempotency_key
        ),
    )
    return out(x)


@router.post("/invoices/{invoice_id}/open")
async def open_invoice(invoice_id: uuid.UUID, request: Request) -> dict[str, Any]:
    return out(await run(request, lambda s: s.open_invoice(invoice_id)))


@router.post("/invoices/{invoice_id}/payments", status_code=201)
async def pay(invoice_id: uuid.UUID, payload: PaymentIn, request: Request) -> dict[str, Any]:
    p, url = await run(request, lambda s: s.initiate_payment(invoice_id, payload.provider))
    return {**out(p), "checkout_url": url}


@router.post("/payments/{payment_id}/reconcile")
async def reconcile(payment_id: uuid.UUID, request: Request) -> dict[str, Any]:
    return out(await run(request, lambda s: s.reconcile(payment_id)))


@webhook_router.post("/{provider}")
async def webhook(provider: str, request: Request) -> dict[str, bool]:
    body = await request.body()
    adapter = getattr(request.app.state, "payment_providers", {}).get(provider)
    if not adapter:
        return {"accepted": False}
    data = await adapter.verify_webhook(
        body=body, signature=request.headers.get("X-Payment-Signature")
    )
    async with request.app.state.session_factory() as session:
        accepted = await service(request, session).ingest(
            provider,
            str(data["event_id"]),
            datetime.fromisoformat(data["occurred_at"]),
            str(data["payment_reference"]),
            str(data["status"]),
            data,
        )
        await session.commit()
        return {"accepted": accepted}
