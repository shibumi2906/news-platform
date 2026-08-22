from __future__ import annotations

import uuid
from typing import Any

from common.auth import require_permission
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from site_domain.models import AdCampaign, AdCreative, AdPlacement, Advertiser

from site_api.advertising import AdvertisingError, AdvertisingRepository, AdvertisingService

admin_router = APIRouter(
    prefix="/api/v1/admin/advertising",
    dependencies=[Depends(require_permission("advertising:manage"))],
)
public_router = APIRouter(prefix="/api/v1/public/ads")


class AdvertiserIn(BaseModel):
    name: str


class PlacementIn(BaseModel):
    code: str
    allowed_kinds: list[str]


class CampaignIn(BaseModel):
    advertiser_id: uuid.UUID
    name: str
    priority: int = 0
    targeting: dict[str, Any] = {}


class CreativeIn(BaseModel):
    campaign_id: uuid.UUID
    placement_id: uuid.UUID
    kind: str
    destination_url: str


class EventIn(BaseModel):
    creative_id: uuid.UUID
    event_id: str


def svc(r: Request, s: Any) -> AdvertisingService:
    return AdvertisingService(AdvertisingRepository(s, r.app.state.settings.instance_id))


async def write(r: Request, fn: Any) -> Any:
    async with r.app.state.session_factory() as s:
        x = await fn(svc(r, s))
        await s.commit()
        return x


@admin_router.post("/advertisers")
async def advertiser(p: AdvertiserIn, r: Request) -> dict[str, str]:
    x = await write(r, lambda s: s.advertiser(p.name))
    return {"id": str(x.id)}


@admin_router.post("/placements")
async def placement(p: PlacementIn, r: Request) -> dict[str, str]:
    x = await write(r, lambda s: s.placement(p.code, p.allowed_kinds))
    return {"id": str(x.id)}


@admin_router.post("/campaigns")
async def campaign(p: CampaignIn, r: Request) -> dict[str, str]:
    x = await write(
        r, lambda s: s.campaign(p.advertiser_id, p.name, priority=p.priority, targeting=p.targeting)
    )
    return {"id": str(x.id)}


@admin_router.post("/creatives")
async def creative(p: CreativeIn, r: Request) -> dict[str, str]:
    x = await write(
        r, lambda s: s.creative(p.campaign_id, p.placement_id, p.kind, p.destination_url)
    )
    return {"id": str(x.id)}


@admin_router.get("/{entity}")
async def list_entities(entity: str, r: Request) -> list[dict[str, Any]]:
    classes = {
        "advertisers": Advertiser,
        "placements": AdPlacement,
        "campaigns": AdCampaign,
        "creatives": AdCreative,
    }
    cls = classes.get(entity)
    if cls is None:
        raise AdvertisingError("not_found", "advertising resource not found", 404)
    async with r.app.state.session_factory() as s:
        return [
            {"id": str(x.id), "status": getattr(x, "status", None)}
            for x in await svc(r, s).repo.list(cls)
        ]


@admin_router.post("/campaigns/{campaign_id}/status")
async def campaign_status(
    campaign_id: uuid.UUID, target: str, r: Request, approved: bool | None = None
) -> dict[str, str]:
    x = await write(r, lambda s: s.transition(campaign_id, target, approved))
    return {"id": str(x.id), "status": x.status}


@admin_router.get("/reporting/campaigns")
async def reporting(r: Request) -> list[dict[str, Any]]:
    async with r.app.state.session_factory() as s:
        return await svc(r, s).report()


@public_router.get("/{placement}")
async def serve(
    placement: str, r: Request, locale: str | None = None, geo: str | None = None
) -> dict[str, Any]:
    async with r.app.state.session_factory() as s:
        x = await svc(r, s).eligible(placement, locale, geo)
        return (
            {"ad": None}
            if not x
            else {
                "ad": {
                    "creative_id": str(x.id),
                    "destination_url": x.destination_url,
                    "disclosure": x.disclosure,
                    "content": x.content,
                }
            }
        )


@public_router.post("/impressions")
async def impression(p: EventIn, r: Request) -> dict[str, bool]:
    return {"accepted": await write(r, lambda s: s.track(p.creative_id, p.event_id, "impression"))}


@public_router.post("/clicks")
async def click(p: EventIn, r: Request) -> dict[str, bool]:
    return {"accepted": await write(r, lambda s: s.track(p.creative_id, p.event_id, "click"))}
