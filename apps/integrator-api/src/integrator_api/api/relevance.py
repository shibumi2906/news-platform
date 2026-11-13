"""Editor-facing relevance model controls and isolated test runs."""

from __future__ import annotations

from uuid import UUID, uuid4

from common.auth import AuthContext, require_permission
from fastapi import APIRouter, Depends, HTTPException, Request
from integrator_domain.ai_quality import rollback
from integrator_domain.models import (
    AIConfigRelease,
    AIQualityPolicy,
    PromptTemplate,
    PromptVersion,
    Topic,
)
from processing_worker.ai_gateway import AIGateway, AIGatewayError
from processing_worker.config import Settings
from processing_worker.prompt_registry import get_active_prompt
from processing_worker.provider_factory import (
    OPENAI_MODEL_RATES,
    _openai_provider,
    build_configured_gateway,
    openai_model_rates,
)
from processing_worker.relevance import relevance_request
from processing_worker.schemas import RelevanceOutput
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from integrator_api.api.ai_admin import TopicInput

editor = Depends(require_permission("topics:manage"))
router = APIRouter(prefix="/api/v1/ai/relevance", dependencies=[editor])


class ModelChoice(BaseModel):
    model: str = Field(min_length=1, max_length=128)


class PreviewInput(BaseModel):
    text: str = Field(min_length=1, max_length=16000)
    topic: TopicInput | None = None
    topic_id: UUID | None = None
    model: str | None = Field(default=None, max_length=128)


def settings_for(request: Request) -> Settings:
    settings = request.app.state.settings
    return Settings(
        instance_id=settings.instance_id,
        database_url=settings.database_url,
        app_env=settings.app_env,
    )


async def active_releases(session: AsyncSession) -> list[AIConfigRelease]:
    rows = (
        await session.scalars(
            select(AIConfigRelease)
            .where(AIConfigRelease.status.in_(["active", "canary"]))
            .order_by(AIConfigRelease.created_at.desc())
        )
    ).all()
    return [row for row in rows if row.audit.get("operation") == "relevance"]


def model_choices(settings: Settings) -> list[str]:
    if not settings.openai_api_key:
        return []
    return list(dict.fromkeys([*OPENAI_MODEL_RATES, settings.openai_model]))


@router.get("/model")
async def get_model(request: Request):
    settings = settings_for(request)
    async with request.app.state.session_factory() as session:
        releases = await active_releases(session)
    active = next((row for row in releases if row.status == "active"), None)
    provider = settings.ai_providers.split(",")[0].strip()
    return {
        "model": active.model
        if active
        else (settings.openai_model if provider == "openai" else "deterministic-v1"),
        "canary": next((row.model for row in releases if row.status == "canary"), None),
        "changed_at": active.created_at if active else None,
        "changed_by": active.audit.get("actor") if active else None,
        "can_rollback": bool(active and active.audit.get("model_only")),
        "options": [
            {"model": model, "input": rates[0], "output": rates[1]}
            for model in model_choices(settings)
            if (rates := openai_model_rates(settings, model))
        ],
    }


async def lock_relevance(session: AsyncSession) -> None:
    await session.execute(
        select(PromptTemplate.id).where(PromptTemplate.operation == "relevance").with_for_update()
    )


@router.put("/model")
async def set_model(payload: ModelChoice, request: Request, actor: AuthContext = editor):
    settings = settings_for(request)
    if payload.model not in model_choices(settings):
        raise HTTPException(422, "Model is not configured on this server")
    async with request.app.state.session_factory() as session, session.begin():
        await lock_relevance(session)
        try:
            prompt = await get_active_prompt(session, "relevance")
        except LookupError as exc:
            raise HTTPException(409, "Configure a relevance prompt first") from exc
        releases = await active_releases(session)
        if any(row.status == "canary" for row in releases):
            raise HTTPException(409, "Finish the active relevance canary before switching models")
        previous = next(iter(releases), None)
        if previous and previous.model == payload.model and previous.provider == "openai":
            return {"model": payload.model}
        for row in releases:
            row.status = "superseded"
        pinned = previous is not None and not previous.audit.get("keep_active_prompt", False)
        session.add(
            AIConfigRelease(
                prompt_version_id=previous.prompt_version_id if pinned and previous else prompt.id,
                provider="openai",
                model=payload.model,
                status="active",
                rollout_percent=100,
                previous_release_id=previous.id if previous else None,
                audit={
                    "operation": "relevance",
                    "model_only": True,
                    "keep_active_prompt": not pinned,
                    "actor": actor.actor,
                },
            )
        )
    return {"model": payload.model}


@router.post("/model/rollback")
async def rollback_model(request: Request, actor: AuthContext = editor):
    async with request.app.state.session_factory() as session, session.begin():
        await lock_relevance(session)
        releases = await active_releases(session)
        if any(row.status == "canary" for row in releases):
            raise HTTPException(409, "Finish the active relevance canary before rolling back")
        active = next(iter(releases), None)
        if active is None or not active.audit.get("model_only"):
            raise HTTPException(409, "No model change to roll back")
        if active.previous_release_id is None and await session.scalar(
            select(AIQualityPolicy.id).where(AIQualityPolicy.operation == "relevance")
        ):
            raise HTTPException(409, "A quality policy requires an active release")
        await rollback(session, active)
        active.audit = {**active.audit, "rolled_back_by": actor.actor}
    return {"rolled_back": True}


@router.post("/preview")
async def preview(payload: PreviewInput, request: Request, actor: AuthContext = editor):
    if not request.app.state.integration_limiter.allow(f"relevance-preview:{actor.actor}"):
        raise HTTPException(429, "Too many previews")
    settings = settings_for(request)
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            prompt = await get_active_prompt(session, "relevance")
        except LookupError as exc:
            raise HTTPException(409, "Configure a relevance prompt first") from exc
        topics = (
            [Topic(id=payload.topic_id or uuid4(), **payload.topic.model_dump())]
            if payload.topic
            else (await session.scalars(select(Topic).where(Topic.is_active))).all()
        )
        if payload.model is not None:
            active = next(
                (row for row in await active_releases(session) if row.status == "active"), None
            )
            if active and not active.audit.get("keep_active_prompt", False):
                pinned = await session.get(PromptVersion, active.prompt_version_id)
                if pinned is not None:
                    prompt = pinned
    if not topics:
        raise HTTPException(422, "Create or activate a topic first")
    if payload.model is not None:
        if payload.model not in model_choices(settings):
            raise HTTPException(422, "Model is not configured on this server")
        gateway = AIGateway(
            [_openai_provider(settings, payload.model)], max_attempts_per_provider=1
        )
    else:
        gateway = build_configured_gateway(settings, factory)
    try:
        response = await gateway.complete(
            relevance_request(prompt.system_prompt, prompt.user_prompt, payload.text, topics)
        )
        result = RelevanceOutput.model_validate(response.output)
    except AIGatewayError as exc:
        raise HTTPException(502, exc.code) from exc
    except ValidationError as exc:
        raise HTTPException(502, "AI returned an invalid relevance result") from exc
    names = {topic.id: topic.name for topic in topics}
    if any(match.topic_id not in names for match in result.matches):
        raise HTTPException(502, "AI returned an unknown topic")
    return {
        "model": response.model,
        "estimated_cost_usd": response.estimated_cost_usd,
        "matches": [
            {**match.model_dump(), "topic": names[match.topic_id]} for match in result.matches
        ],
    }
