from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from site_domain.models import AdCampaign, AdCreative, AdDeliveryEvent, AdPlacement, Advertiser
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

TRANSITIONS = {
    "draft": {"active", "cancelled"},
    "active": {"paused", "completed", "cancelled"},
    "paused": {"active", "cancelled"},
}


class AdvertisingError(Exception):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code, self.message, self.status_code = code, message, status
        super().__init__(message)


class AdvertisingRepository:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session, self.tenant_id = session, tenant_id

    async def get(self, cls: Any, id: uuid.UUID) -> Any | None:
        return (
            await self.session.execute(
                select(cls).where(cls.id == id, cls.tenant_id == self.tenant_id)
            )
        ).scalar_one_or_none()

    async def list(self, cls: Any) -> list[Any]:
        return list(
            (
                await self.session.execute(select(cls).where(cls.tenant_id == self.tenant_id))
            ).scalars()
        )

    async def add(self, row: Any) -> Any:
        self.session.add(row)
        await self.session.flush()
        return row


class AdvertisingService:
    def __init__(self, repo: AdvertisingRepository) -> None:
        self.repo = repo

    async def advertiser(self, name: str) -> Advertiser:
        return cast(
            Advertiser, await self.repo.add(Advertiser(tenant_id=self.repo.tenant_id, name=name))
        )

    async def placement(self, code: str, kinds: list[str]) -> AdPlacement:
        if not kinds:
            raise AdvertisingError("invalid_placement", "placement requires creative kinds")
        return cast(
            AdPlacement,
            await self.repo.add(
                AdPlacement(tenant_id=self.repo.tenant_id, code=code, allowed_kinds=kinds)
            ),
        )

    async def campaign(self, advertiser_id: uuid.UUID, name: str, **values: Any) -> AdCampaign:
        if not await self.repo.get(Advertiser, advertiser_id):
            raise AdvertisingError("not_found", "advertiser not found", 404)
        return cast(
            AdCampaign,
            await self.repo.add(
                AdCampaign(
                    tenant_id=self.repo.tenant_id, advertiser_id=advertiser_id, name=name, **values
                )
            ),
        )

    async def transition(
        self, id: uuid.UUID, target: str, approved: bool | None = None
    ) -> AdCampaign:
        x = await self._get(AdCampaign, id, "campaign")
        if approved is not None:
            x.approved = approved
        if target != x.status and target not in TRANSITIONS.get(x.status, set()):
            raise AdvertisingError("invalid_state_transition", "invalid campaign transition")
        if target == "active" and not x.approved:
            raise AdvertisingError("campaign_unapproved", "campaign must be approved", 409)
        x.status = target
        return cast(AdCampaign, x)

    async def creative(
        self, campaign_id: uuid.UUID, placement_id: uuid.UUID, kind: str, url: str, **values: Any
    ) -> AdCreative:
        await self._get(AdCampaign, campaign_id, "campaign")
        p = await self._get(AdPlacement, placement_id, "placement")
        if kind not in p.allowed_kinds:
            raise AdvertisingError("incompatible_placement", "creative kind not allowed")
        return cast(
            AdCreative,
            await self.repo.add(
                AdCreative(
                    tenant_id=self.repo.tenant_id,
                    campaign_id=campaign_id,
                    placement_id=placement_id,
                    kind=kind,
                    destination_url=url,
                    **values,
                )
            ),
        )

    async def eligible(self, code: str, locale: str | None, geo: str | None) -> AdCreative | None:
        now = datetime.now(UTC)
        p = (
            await self.repo.session.execute(
                select(AdPlacement).where(
                    AdPlacement.tenant_id == self.repo.tenant_id,
                    AdPlacement.code == code,
                    AdPlacement.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if not p:
            return None
        rows = (
            await self.repo.session.execute(
                select(AdCreative, AdCampaign)
                .join(AdCampaign)
                .where(
                    AdCreative.tenant_id == self.repo.tenant_id,
                    AdCreative.placement_id == p.id,
                    AdCreative.status == "approved",
                    AdCampaign.status == "active",
                    AdCampaign.approved.is_(True),
                )
                .order_by(AdCampaign.priority.desc(), AdCreative.id)
            )
        ).all()
        for c, x in rows:
            t = x.targeting
            if (
                c.rights_expires_at
                and c.rights_expires_at <= now
                or x.starts_at
                and now < x.starts_at
                or x.ends_at
                and now >= x.ends_at
            ):
                continue
            if (
                t.get("sites")
                and str(self.repo.tenant_id) not in t["sites"]
                or t.get("locales")
                and locale not in t["locales"]
                or t.get("geo")
                and geo not in t["geo"]
            ):
                continue
            if (
                x.impression_limit is not None
                and await self._count(c.id, "impression") >= x.impression_limit
            ):
                continue
            return cast(AdCreative, c)
        return None

    async def track(self, creative_id: uuid.UUID, event_id: str, typ: str) -> bool:
        c = await self._get(AdCreative, creative_id, "creative")
        if typ not in {"impression", "click"}:
            raise AdvertisingError("invalid_event", "unknown delivery event")
        try:
            async with self.repo.session.begin_nested():
                self.repo.session.add(
                    AdDeliveryEvent(
                        tenant_id=self.repo.tenant_id,
                        event_id=event_id,
                        creative_id=c.id,
                        campaign_id=c.campaign_id,
                        placement_id=c.placement_id,
                        event_type=typ,
                        occurred_at=datetime.now(UTC),
                    )
                )
                await self.repo.session.flush()
        except IntegrityError:
            return False
        return True

    async def report(self) -> list[dict[str, Any]]:
        rows = (
            await self.repo.session.execute(
                select(AdDeliveryEvent.campaign_id, AdDeliveryEvent.event_type, func.count())
                .where(AdDeliveryEvent.tenant_id == self.repo.tenant_id)
                .group_by(AdDeliveryEvent.campaign_id, AdDeliveryEvent.event_type)
            )
        ).all()
        data: dict[str, dict[str, Any]] = {}
        for cid, typ, count in rows:
            data.setdefault(str(cid), {"campaign_id": str(cid), "impressions": 0, "clicks": 0})[
                f"{typ}s"
            ] = count
        return list(data.values())

    async def _get(self, cls: Any, id: uuid.UUID, label: str) -> Any:
        x = await self.repo.get(cls, id)
        if not x:
            raise AdvertisingError("not_found", f"{label} not found", 404)
        return x

    async def _count(self, creative: uuid.UUID, typ: str) -> int:
        return int(
            (
                await self.repo.session.execute(
                    select(func.count())
                    .select_from(AdDeliveryEvent)
                    .where(
                        AdDeliveryEvent.tenant_id == self.repo.tenant_id,
                        AdDeliveryEvent.creative_id == creative,
                        AdDeliveryEvent.event_type == typ,
                    )
                )
            ).scalar_one()
        )
