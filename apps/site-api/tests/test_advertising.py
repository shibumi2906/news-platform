from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from common.db import Base, create_engine, create_session_factory
from site_api.advertising import AdvertisingError, AdvertisingRepository, AdvertisingService


@pytest.fixture
async def service() -> AsyncGenerator[AdvertisingService, None]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    session = create_session_factory(engine)()
    yield AdvertisingService(AdvertisingRepository(session, uuid.uuid4()))
    await session.close()
    await engine.dispose()


async def test_lifecycle_eligibility_tracking_and_reporting(service: AdvertisingService) -> None:
    advertiser = await service.advertiser("Acme")
    placement = await service.placement("hero", ["image"])
    campaign = await service.campaign(
        advertiser.id, "Launch", priority=2, targeting={"locales": ["en"], "geo": ["IL"]}
    )
    creative = await service.creative(
        campaign.id, placement.id, "image", "https://example.test", status="approved"
    )
    assert await service.eligible("hero", "en", "IL") is None
    await service.transition(campaign.id, "active", approved=True)
    selected = await service.eligible("hero", "en", "IL")
    assert selected is not None and selected.id == creative.id
    assert await service.eligible("hero", "fr", "IL") is None
    assert await service.track(creative.id, "i1", "impression")
    assert not await service.track(creative.id, "i1", "impression")
    assert await service.track(creative.id, "c1", "click")
    assert (await service.report())[0]["clicks"] == 1


async def test_isolation_transition_and_compatibility(service: AdvertisingService) -> None:
    other = AdvertisingService(AdvertisingRepository(service.repo.session, uuid.uuid4()))
    advertiser = await service.advertiser("A")
    placement = await service.placement("x", ["text"])
    campaign = await service.campaign(advertiser.id, "C")
    assert await other.repo.get(type(advertiser), advertiser.id) is None
    with pytest.raises(AdvertisingError):
        await service.transition(campaign.id, "paused")
    with pytest.raises(AdvertisingError):
        await service.creative(campaign.id, placement.id, "image", "https://example.test")
