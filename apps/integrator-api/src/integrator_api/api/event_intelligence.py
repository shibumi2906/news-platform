"""Admin review and reversible controls for semantic event clustering."""
# ruff: noqa: E501

from __future__ import annotations

from typing import cast
from uuid import UUID

from common.auth import require_permission
from fastapi import APIRouter, Depends, HTTPException, Request
from integrator_domain.event_intelligence import (
    merge_events,
    resolve_review,
    reverse_operation,
    split_event,
)
from integrator_domain.models import EventClusteringPolicy, EventMatchReview
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/ai/events", tags=["event-intelligence"], dependencies=[Depends(require_permission("topics:manage"))])


class ReviewOutput(BaseModel):
    id: UUID
    source_material_id: UUID
    proposed_event_id: UUID
    candidate_event_id: UUID
    score: float
    evidence: dict[str, object]
    status: str


class ReviewResolution(BaseModel):
    accept: bool


class MergeInput(BaseModel):
    source_event_id: UUID


class SplitInput(BaseModel):
    material_ids: list[UUID] = Field(min_length=1)


class PolicyInput(BaseModel):
    auto_merge_threshold: float = Field(ge=0, le=1)
    review_threshold: float = Field(ge=0, le=1)
    candidate_window_hours: int = Field(ge=1, le=8760)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> PolicyInput:
        if self.auto_merge_threshold < self.review_threshold:
            raise ValueError("auto_merge_threshold must be >= review_threshold")
        return self


class PolicyOutput(PolicyInput):
    id: UUID


async def _policy(request: Request) -> EventClusteringPolicy:
    async with request.app.state.session_factory() as session, session.begin():
        policy = cast(EventClusteringPolicy | None, await session.scalar(select(EventClusteringPolicy).order_by(EventClusteringPolicy.created_at)))
        if policy is None:
            policy = EventClusteringPolicy()
            session.add(policy)
            await session.flush()
        await session.refresh(policy)
        return policy


@router.get("/policy", response_model=PolicyOutput)
async def get_policy(request: Request) -> PolicyOutput:
    policy = await _policy(request)
    return PolicyOutput.model_validate(policy, from_attributes=True)


@router.put("/policy", response_model=PolicyOutput)
async def update_policy(payload: PolicyInput, request: Request) -> PolicyOutput:
    async with request.app.state.session_factory() as session, session.begin():
        policy = cast(EventClusteringPolicy | None, await session.scalar(select(EventClusteringPolicy).order_by(EventClusteringPolicy.created_at)))
        if policy is None:
            policy = EventClusteringPolicy()
            session.add(policy)
        policy.auto_merge_threshold = payload.auto_merge_threshold
        policy.review_threshold = payload.review_threshold
        policy.candidate_window_hours = payload.candidate_window_hours
        await session.flush()
        return PolicyOutput.model_validate(policy, from_attributes=True)


@router.get("/reviews", response_model=list[ReviewOutput])
async def list_reviews(request: Request, status: str = "pending") -> list[ReviewOutput]:
    async with request.app.state.session_factory() as session:
        rows = (await session.execute(select(EventMatchReview).where(EventMatchReview.status == status).order_by(EventMatchReview.created_at))).scalars()
        return [ReviewOutput.model_validate(row, from_attributes=True) for row in rows]


@router.post("/reviews/{review_id}", response_model=ReviewOutput)
async def resolve_event_review(review_id: UUID, payload: ReviewResolution, request: Request) -> ReviewOutput:
    async with request.app.state.session_factory() as session, session.begin():
        try:
            review = await resolve_review(session, review_id=review_id, accept=payload.accept, actor_id="admin")
        except LookupError as exc:
            raise HTTPException(404, "pending event review not found") from exc
        return ReviewOutput.model_validate(review, from_attributes=True)


@router.post("/{event_id}/merge")
async def merge_event(event_id: UUID, payload: MergeInput, request: Request) -> dict[str, str]:
    async with request.app.state.session_factory() as session, session.begin():
        try:
            event = await merge_events(session, target_event_id=event_id, source_event_id=payload.source_event_id, actor_id="admin")
        except (LookupError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"event_id": str(event.id), "status": "merged"}


@router.post("/{event_id}/split")
async def split_event_route(event_id: UUID, payload: SplitInput, request: Request) -> dict[str, str]:
    async with request.app.state.session_factory() as session, session.begin():
        try:
            event = await split_event(session, event_id=event_id, material_ids=set(payload.material_ids), actor_id="admin")
        except LookupError as exc:
            raise HTTPException(404, "active event not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"event_id": str(event.id), "status": "split"}


@router.post("/operations/{operation_id}/reverse")
async def reverse_event_operation(operation_id: UUID, request: Request) -> dict[str, str]:
    async with request.app.state.session_factory() as session, session.begin():
        try:
            event = await reverse_operation(session, operation_id=operation_id, actor_id="admin")
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"event_id": str(event.id), "status": "reversed"}
