"""Reversible, auditable event-cluster mutations shared by worker and admin API."""
# ruff: noqa: E501

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from integrator_domain.models.event import (
    Event,
    EventClusterOperation,
    EventMatchReview,
    EventMaterial,
)


async def merge_events(
    session: AsyncSession, *, target_event_id: UUID, source_event_id: UUID, actor_id: str | None
) -> Event:
    if target_event_id == source_event_id:
        raise ValueError("cannot merge an event into itself")
    target = await session.get(Event, target_event_id)
    source = await session.get(Event, source_event_id)
    if target is None or source is None or target.status != "active" or source.status != "active":
        raise LookupError("active event not found")
    members = list(
        (
            await session.execute(select(EventMaterial).where(EventMaterial.event_id == source.id))
        ).scalars()
    )
    for member in members:
        duplicate = await session.scalar(
            select(EventMaterial.id).where(
                EventMaterial.event_id == target.id,
                EventMaterial.source_material_id == member.source_material_id,
            )
        )
        if duplicate is None:
            member.event_id = target.id
        else:
            await session.delete(member)
    source.status = "merged"
    source.merged_into_event_id = target.id
    session.add(
        EventClusterOperation(
            operation="merge",
            target_event_id=target.id,
            source_event_id=source.id,
            actor_id=actor_id,
            payload={"moved_material_ids": [str(member.source_material_id) for member in members]},
        )
    )
    return target


async def split_event(
    session: AsyncSession, *, event_id: UUID, material_ids: set[UUID], actor_id: str | None
) -> Event:
    event = await session.get(Event, event_id)
    if event is None or event.status != "active":
        raise LookupError("active event not found")
    members = list(
        (
            await session.execute(
                select(EventMaterial).where(
                    EventMaterial.event_id == event.id,
                    EventMaterial.source_material_id.in_(material_ids),
                )
            )
        ).scalars()
    )
    member_count = await session.scalar(
        select(func.count()).select_from(EventMaterial).where(EventMaterial.event_id == event.id)
    )
    if not members or len(members) == member_count:
        raise ValueError("split must move a non-empty proper subset")
    new_event = Event(
        source_material_id=None,
        stage=event.stage,
        title=event.title,
        summary=event.summary,
        cluster_confidence=event.cluster_confidence,
    )
    session.add(new_event)
    await session.flush()
    for member in members:
        member.event_id = new_event.id
        member.decision = "split"
    session.add(
        EventClusterOperation(
            operation="split",
            target_event_id=new_event.id,
            source_event_id=event.id,
            actor_id=actor_id,
            payload={"moved_material_ids": [str(member.source_material_id) for member in members]},
        )
    )
    return new_event


async def reverse_operation(
    session: AsyncSession, *, operation_id: UUID, actor_id: str | None
) -> Event:
    """Undo a merge or split using the immutable operation payload."""
    operation = await session.get(EventClusterOperation, operation_id)
    if operation is None or operation.operation not in {"merge", "split"}:
        raise LookupError("reversible event operation not found")
    target = await session.get(Event, operation.target_event_id)
    source = await session.get(Event, operation.source_event_id)
    if target is None or source is None:
        raise LookupError("event operation references missing event")
    material_ids = {UUID(value) for value in operation.payload.get("moved_material_ids", [])}
    members = list(
        (
            await session.execute(
                select(EventMaterial).where(
                    EventMaterial.event_id == target.id,
                    EventMaterial.source_material_id.in_(material_ids),
                )
            )
        ).scalars()
    )
    if not members:
        raise ValueError("event operation has no reversible memberships")
    for member in members:
        member.event_id = source.id
        member.decision = "reversed"
    if operation.operation == "merge":
        source.status = "active"
        source.merged_into_event_id = None
    else:
        target.status = "merged"
        target.merged_into_event_id = source.id
    session.add(
        EventClusterOperation(
            operation=f"reverse_{operation.operation}",
            target_event_id=source.id,
            source_event_id=target.id,
            actor_id=actor_id,
            payload={"reversed_operation_id": str(operation.id), "moved_material_ids": list(map(str, material_ids))},
        )
    )
    return source


async def resolve_review(
    session: AsyncSession, *, review_id: UUID, accept: bool, actor_id: str
) -> EventMatchReview:
    review = await session.get(EventMatchReview, review_id)
    if review is None or review.status != "pending":
        raise LookupError("pending review not found")
    if accept:
        await merge_events(
            session,
            target_event_id=review.candidate_event_id,
            source_event_id=review.proposed_event_id,
            actor_id=actor_id,
        )
        review.status = "accepted"
    else:
        review.status = "rejected"
    review.resolved_by_actor_id = actor_id
    return review
