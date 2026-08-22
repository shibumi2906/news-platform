from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.billing import (
    BillingError,
    BillingRepository,
    BillingService,
    ProviderCheckout,
    ProviderPaymentState,
    ProviderUnconfiguredError,
    transition_invoice,
    transition_payment,
    validate_money,
)
from sqlalchemy.ext.asyncio import AsyncSession


class FakeProvider:
    name = "fake"
    fail = False
    state = "succeeded"

    async def initiate(self, **_: object) -> ProviderCheckout:
        if self.fail:
            raise RuntimeError("down")
        return ProviderCheckout("external-1", "https://checkout.invalid/1")

    async def verify_webhook(self, **_: object) -> dict[str, object]:
        return {}

    async def reconcile(self, reference: str) -> ProviderPaymentState:
        return ProviderPaymentState(reference, self.state, datetime.now(UTC))


@pytest.fixture
async def services() -> AsyncGenerator[tuple[BillingService, BillingService, AsyncSession], None]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    session = factory()
    provider = FakeProvider()
    yield (
        BillingService(BillingRepository(session, uuid.uuid4()), {"fake": provider}),
        BillingService(BillingRepository(session, uuid.uuid4()), {"fake": provider}),
        session,
    )
    await session.close()
    await engine.dispose()


async def test_repository_tenant_idempotency_and_lifecycle(
    services: tuple[BillingService, BillingService, AsyncSession],
) -> None:
    service, other, session = services
    customer = await service.create_customer("x@example.test", {})
    invoice, created = await service.create_invoice(customer.id, 123, "USD", "key")
    same, again = await service.create_invoice(customer.id, 123, "USD", "key")
    assert created and not again and invoice.id == same.id
    assert await other.repo.customer(customer.id) is None
    await service.open_invoice(invoice.id)
    payment, _ = await service.initiate_payment(invoice.id, "fake")
    assert payment.status == "pending"
    assert await service.ingest("fake", "evt-1", datetime.now(UTC), "external-1", "succeeded", {})
    assert payment.status == "succeeded" and invoice.status == "paid"
    await session.commit()


async def test_state_money_webhook_order_and_reconciliation(
    services: tuple[BillingService, BillingService, AsyncSession],
) -> None:
    service, _, _ = services
    customer = await service.create_customer(None, {})
    invoice, _ = await service.create_invoice(customer.id, 1, "ILS", "other")
    with pytest.raises(BillingError):
        transition_invoice(invoice, "paid")
    await service.open_invoice(invoice.id)
    payment, _ = await service.initiate_payment(invoice.id, "fake")
    now = datetime.now(UTC)
    assert await service.ingest("fake", "unknown", now, "missing", "succeeded", {})
    assert await service.ingest("fake", "evt", now, "external-1", "authorized", {})
    assert not await service.ingest("fake", "evt", now, "external-1", "authorized", {})
    assert await service.ingest("fake", "old", now - timedelta(days=1), "external-1", "failed", {})
    assert payment.status == "authorized"
    await service.reconcile(payment.id)
    assert payment.status == "succeeded"
    await service.reconcile(payment.id)
    with pytest.raises(BillingError):
        transition_payment(payment, "failed")
    for amount, currency in [(0, "USD"), (-1, "USD"), (1, "usd"), (1, "XXX")]:
        with pytest.raises(BillingError):
            validate_money(amount, currency)


async def test_provider_unconfigured_and_error(
    services: tuple[BillingService, BillingService, AsyncSession],
) -> None:
    service, _, _ = services
    customer = await service.create_customer(None, {})
    invoice, _ = await service.create_invoice(customer.id, 1, "USD", "third")
    await service.open_invoice(invoice.id)
    with pytest.raises(ProviderUnconfiguredError):
        await service.initiate_payment(invoice.id, "none")
    provider = service.providers["fake"]
    provider.fail = True  # type: ignore[attr-defined]
    with pytest.raises(BillingError, match="provider"):
        await service.initiate_payment(invoice.id, "fake")
