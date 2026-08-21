"""Billing services and provider boundary; no production provider is bundled."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from site_domain.models import (
    BillingAuditEntry,
    BillingCustomer,
    BillingInvoice,
    BillingPayment,
    BillingWebhookEvent,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

INVOICE_TRANSITIONS = {"draft": {"open", "cancelled"}, "open": {"paid", "void", "cancelled"}}
PAYMENT_TRANSITIONS = {
    "pending": {"authorized", "succeeded", "failed", "cancelled"},
    "authorized": {"succeeded", "cancelled"},
    "succeeded": {"refunded"},
}
ISO_CURRENCIES = frozenset(
    {
        "AED",
        "ARS",
        "AUD",
        "BRL",
        "CAD",
        "CHF",
        "CNY",
        "CZK",
        "DKK",
        "EUR",
        "GBP",
        "HKD",
        "HUF",
        "ILS",
        "INR",
        "JPY",
        "KRW",
        "MXN",
        "NOK",
        "NZD",
        "PLN",
        "SEK",
        "SGD",
        "THB",
        "TRY",
        "USD",
        "ZAR",
    }
)


class BillingError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


class ProviderUnconfiguredError(BillingError):
    def __init__(self) -> None:
        super().__init__("provider_unavailable", "payment provider is not configured", 503)


@dataclass(frozen=True)
class ProviderCheckout:
    reference: str
    checkout_url: str


@dataclass(frozen=True)
class ProviderPaymentState:
    reference: str
    status: str
    occurred_at: datetime


class PaymentProvider(Protocol):
    name: str

    async def initiate(
        self, *, payment: BillingPayment, invoice: BillingInvoice, customer: BillingCustomer
    ) -> ProviderCheckout: ...
    async def verify_webhook(self, *, body: bytes, signature: str | None) -> dict[str, Any]: ...
    async def reconcile(self, reference: str) -> ProviderPaymentState: ...


class BillingRepository:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session, self.tenant_id = session, tenant_id

    async def customer(self, id: uuid.UUID) -> BillingCustomer | None:
        return (
            await self.session.execute(
                select(BillingCustomer).where(
                    BillingCustomer.id == id, BillingCustomer.tenant_id == self.tenant_id
                )
            )
        ).scalar_one_or_none()

    async def invoice(self, id: uuid.UUID) -> BillingInvoice | None:
        return (
            await self.session.execute(
                select(BillingInvoice).where(
                    BillingInvoice.id == id, BillingInvoice.tenant_id == self.tenant_id
                )
            )
        ).scalar_one_or_none()

    async def payment(self, id: uuid.UUID) -> BillingPayment | None:
        return (
            await self.session.execute(
                select(BillingPayment).where(
                    BillingPayment.id == id, BillingPayment.tenant_id == self.tenant_id
                )
            )
        ).scalar_one_or_none()

    async def invoices(self) -> list[BillingInvoice]:
        return list(
            (
                await self.session.execute(
                    select(BillingInvoice).where(BillingInvoice.tenant_id == self.tenant_id)
                )
            ).scalars()
        )

    async def payment_by_reference(self, provider: str, reference: str) -> BillingPayment | None:
        return (
            await self.session.execute(
                select(BillingPayment).where(
                    BillingPayment.tenant_id == self.tenant_id,
                    BillingPayment.provider == provider,
                    BillingPayment.provider_reference == reference,
                )
            )
        ).scalar_one_or_none()

    async def add_customer(self, email: str | None, attributes: dict[str, Any]) -> BillingCustomer:
        x = BillingCustomer(tenant_id=self.tenant_id, email=email, attributes=attributes)
        self.session.add(x)
        await self.session.flush()
        return x

    async def add_invoice(
        self, customer_id: uuid.UUID, amount_minor: int, currency: str, key: str
    ) -> tuple[BillingInvoice, bool]:
        x = (
            await self.session.execute(
                select(BillingInvoice).where(
                    BillingInvoice.tenant_id == self.tenant_id,
                    BillingInvoice.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if x:
            return x, False
        x = BillingInvoice(
            tenant_id=self.tenant_id,
            customer_id=customer_id,
            amount_minor=amount_minor,
            currency=currency,
            idempotency_key=key,
        )
        self.session.add(x)
        await self.session.flush()
        return x, True

    def audit(
        self, typ: str, id: uuid.UUID, action: str, details: dict[str, Any] | None = None
    ) -> None:
        self.session.add(
            BillingAuditEntry(
                tenant_id=self.tenant_id,
                aggregate_type=typ,
                aggregate_id=id,
                action=action,
                details=details or {},
                created_at=datetime.now(UTC),
            )
        )


def validate_money(amount_minor: int, currency: str) -> None:
    if isinstance(amount_minor, bool) or amount_minor <= 0:
        raise BillingError("invalid_money", "amount_minor must be a positive integer")
    if currency not in ISO_CURRENCIES:
        raise BillingError("invalid_currency", "currency must be a supported ISO 4217 code")


def transition_invoice(x: BillingInvoice, target: str) -> bool:
    if x.status == target:
        return False
    if target not in INVOICE_TRANSITIONS.get(x.status, set()):
        raise BillingError("invalid_state_transition", "invalid invoice state transition")
    x.status = target
    return True


def transition_payment(x: BillingPayment, target: str) -> bool:
    if x.status == target:
        return False
    if target not in PAYMENT_TRANSITIONS.get(x.status, set()):
        raise BillingError("invalid_state_transition", "invalid payment state transition")
    x.status = target
    return True


class BillingService:
    def __init__(self, repo: BillingRepository, providers: dict[str, PaymentProvider]) -> None:
        self.repo, self.providers = repo, providers

    async def create_customer(
        self, email: str | None, attributes: dict[str, Any]
    ) -> BillingCustomer:
        x = await self.repo.add_customer(email, attributes)
        self.repo.audit("customer", x.id, "created")
        return x

    async def create_invoice(
        self, customer_id: uuid.UUID, amount_minor: int, currency: str, key: str
    ) -> tuple[BillingInvoice, bool]:
        validate_money(amount_minor, currency)
        c = await self._customer(customer_id)
        if c.status != "active":
            raise BillingError("customer_inactive", "customer is not active", 409)
        x, created = await self.repo.add_invoice(customer_id, amount_minor, currency, key)
        if created:
            self.repo.audit("invoice", x.id, "created")
        return x, created

    async def open_invoice(self, id: uuid.UUID) -> BillingInvoice:
        x = await self._invoice(id)
        transition_invoice(x, "open")
        self.repo.audit("invoice", x.id, "opened")
        return x

    async def initiate_payment(
        self, id: uuid.UUID, provider_name: str
    ) -> tuple[BillingPayment, str]:
        invoice = await self._invoice(id)
        if invoice.status != "open":
            raise BillingError("invoice_not_open", "payment requires an open invoice", 409)
        provider = self.providers.get(provider_name)
        if not provider:
            raise ProviderUnconfiguredError()
        p = BillingPayment(
            tenant_id=self.repo.tenant_id,
            invoice_id=invoice.id,
            amount_minor=invoice.amount_minor,
            currency=invoice.currency,
            provider=provider_name,
        )
        self.repo.session.add(p)
        await self.repo.session.flush()
        try:
            checkout = await provider.initiate(
                payment=p, invoice=invoice, customer=await self._customer(invoice.customer_id)
            )
        except Exception as e:
            raise BillingError(
                "provider_error", "payment provider rejected the request", 502
            ) from e
        if not checkout.reference:
            raise BillingError(
                "provider_error", "provider returned an empty payment reference", 502
            )
        p.provider_reference = checkout.reference
        self.repo.audit("payment", p.id, "initiated")
        return p, checkout.checkout_url

    async def ingest(
        self,
        provider: str,
        event_id: str,
        occurred_at: datetime,
        reference: str,
        status: str,
        payload: dict[str, Any],
    ) -> bool:
        try:
            async with self.repo.session.begin_nested():
                self.repo.session.add(
                    BillingWebhookEvent(
                        provider=provider,
                        provider_event_id=event_id,
                        occurred_at=occurred_at,
                        payload=payload,
                        status="received",
                    )
                )
                await self.repo.session.flush()
        except IntegrityError:
            return False
        p = await self.repo.payment_by_reference(provider, reference)
        if not p:
            return True
        if p.provider_updated_at and occurred_at < p.provider_updated_at:
            return True
        if status not in PAYMENT_TRANSITIONS.get(p.status, set()) and status != p.status:
            return True
        if transition_payment(p, status):
            self.repo.audit("payment", p.id, "webhook_state_changed", {"status": status})
        p.provider_updated_at = occurred_at
        if p.status == "succeeded":
            i = await self._invoice(p.invoice_id)
            if i.status == "open":
                transition_invoice(i, "paid")
        return True

    async def reconcile(self, id: uuid.UUID) -> BillingPayment:
        p = await self._payment(id)
        provider = self.providers.get(p.provider or "")
        if not provider or not p.provider_reference:
            raise ProviderUnconfiguredError()
        try:
            state = await provider.reconcile(p.provider_reference)
        except Exception as e:
            raise BillingError(
                "provider_error", "payment provider reconciliation failed", 502
            ) from e
        await self.ingest(
            p.provider or "",
            f"reconcile:{p.provider_reference}:{state.occurred_at.isoformat()}:{state.status}",
            state.occurred_at,
            state.reference,
            state.status,
            {"source": "reconciliation"},
        )
        return p

    async def _customer(self, id: uuid.UUID) -> BillingCustomer:
        x = await self.repo.customer(id)
        if not x:
            raise BillingError("not_found", "billing customer not found", 404)
        return x

    async def _invoice(self, id: uuid.UUID) -> BillingInvoice:
        x = await self.repo.invoice(id)
        if not x:
            raise BillingError("not_found", "billing invoice not found", 404)
        return x

    async def _payment(self, id: uuid.UUID) -> BillingPayment:
        x = await self.repo.payment(id)
        if not x:
            raise BillingError("not_found", "billing payment not found", 404)
        return x
