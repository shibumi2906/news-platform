"""Signed, paginated material feed for registered downstream sites."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from common.signing import verify
from common.time import utc_now
from contracts.package import SCHEMA_VERSION
from fastapi import APIRouter, Header, HTTPException, Request, Response
from integrator_domain.models import CanonicalNewsPackage, SiteConnection
from pydantic import AwareDatetime, BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import String, and_, case, cast, func, or_, select, update

from integrator_api.api.materials import topic_filter

router = APIRouter(prefix="/api/v1/site-feed")


class Cursor(BaseModel):
    created_at: AwareDatetime
    id: UUID


class FeedQuery(BaseModel):
    topic: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=255)
    cursor: Cursor | None = None
    limit: int = Field(default=50, ge=1, le=200)


@router.post("/materials")
async def fetch_materials(
    payload: FeedQuery,
    request: Request,
    response: Response,
    connection_id: Annotated[UUID, Header(alias="X-Connection-Id")],
    timestamp: Annotated[str, Header(alias="X-Timestamp", max_length=64)],
    nonce: Annotated[str, Header(alias="X-Nonce", pattern=r"^[A-Za-z0-9._-]{16,128}$")],
    signature: Annotated[str, Header(alias="X-Signature", pattern=r"^[0-9a-f]{64}$")],
    key_id: Annotated[str, Header(alias="X-Signing-Key-Id", max_length=64)] = "legacy",
):
    response.headers["Cache-Control"] = "no-store"
    now = utc_now()
    try:
        sent_at = datetime.fromisoformat(timestamp)
        if abs((now - sent_at).total_seconds()) > 300:
            raise ValueError
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(401, "Invalid request timestamp") from exc

    async with request.app.state.session_factory() as session, session.begin():
        connection = await session.get(SiteConnection, connection_id)
        if not connection or not connection.is_active or connection.delivery_mode != "pull":
            raise HTTPException(401, "Invalid connection credentials")
        secret = None
        if key_id == connection.active_key_id:
            secret = connection.hmac_secret
        elif key_id == connection.previous_key_id:
            secret = connection.previous_hmac_secret
        if not secret or not verify(
            secret,
            timestamp=timestamp,
            nonce=nonce,
            idempotency_key="site-feed/materials",
            body=await request.body(),
            signature=signature,
        ):
            raise HTTPException(401, "Invalid connection credentials")

        try:
            async with Redis.from_url(
                request.app.state.settings.redis_url, socket_timeout=2
            ) as redis:
                fresh = await redis.set(
                    f"site-feed:nonce:{connection_id}:{nonce}", "1", ex=601, nx=True
                )
        except RedisError as exc:
            raise HTTPException(503, "Site feed authentication temporarily unavailable") from exc
        if not fresh:
            raise HTTPException(409, "Request already received")

        package = CanonicalNewsPackage
        row_time = package.created_at
        query = select(package).where(topic_filter(session, payload.topic))
        if session.get_bind().dialect.name == "sqlite":
            raw_time = cast(row_time, String)
            row_time = case(
                (func.length(raw_time) == 19, raw_time + ".000000"), else_=raw_time
            )
        if payload.cursor:
            cursor_time = payload.cursor.created_at.astimezone(UTC)
            if session.get_bind().dialect.name == "sqlite":
                cursor_time = cursor_time.strftime("%Y-%m-%d %H:%M:%S.%f")
            query = query.where(
                or_(
                    row_time > cursor_time,
                    and_(
                        row_time == cursor_time,
                        package.id > payload.cursor.id,
                    ),
                )
            )
        rows = (
            await session.scalars(query.order_by(row_time, package.id).limit(payload.limit + 1))
        ).all()
        page = rows[: payload.limit]
        last = page[-1] if page else None
        await session.execute(
            update(SiteConnection)
            .where(
                SiteConnection.id == connection_id,
                SiteConnection.is_active,
                SiteConnection.delivery_mode == "pull",
                or_(SiteConnection.last_pull_at.is_(None), SiteConnection.last_pull_at < now),
            )
            .values(last_pull_at=now, updated_at=func.now())
        )
        return {
            "items": [
                {
                    "schema_version": SCHEMA_VERSION,
                    **{
                        field: getattr(row, field)
                        for field in (
                            "package_id",
                            "package_version",
                            "event_id",
                            "event_stage",
                            "instance_id",
                            "operation",
                            "revision_reason",
                            "content",
                            "facts",
                            "entities",
                            "taxonomy",
                            "topics",
                            "categories",
                            "regions",
                            "geographies",
                            "sources",
                            "language_versions",
                            "media",
                            "ai_provenance",
                            "rights",
                            "confidence",
                            "warnings",
                            "created_at",
                            "updated_at",
                        )
                    },
                }
                for row in page
            ],
            "has_more": len(rows) > payload.limit,
            "cursor": {
                "id": last.id,
                "created_at": last.created_at.replace(tzinfo=UTC)
                if last.created_at.tzinfo is None
                else last.created_at,
            }
            if last
            else payload.cursor,
        }
