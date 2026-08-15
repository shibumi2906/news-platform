from __future__ import annotations
# ruff: noqa

from typing import Any
from uuid import UUID

from common.auth import require_permission
from common.logging import get_logger
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from integrator_domain.models import (
    AIConfigRelease,
    AIOperationRun,
    AIEvalSet,
    AIQualityPolicy,
    LanguageConfig,
    PromptTemplate,
    PromptVersion,
    TerminologyEntry,
    Topic,
)
from integrator_domain.ai_quality import promote, rollback
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1/ai",
    tags=["ai-admin"],
    dependencies=[Depends(require_permission("topics:manage"))],
)
logger = get_logger(__name__)


@router.get("/quality/telemetry")
async def quality_telemetry(request: Request) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        rows = await session.execute(select(AIOperationRun.provider, AIOperationRun.model, func.count(), func.avg(AIOperationRun.latency_ms), func.sum(AIOperationRun.prompt_tokens), func.sum(AIOperationRun.completion_tokens), func.sum(AIOperationRun.estimated_cost_usd), func.sum(case((AIOperationRun.status == "failed", 1), else_=0))).group_by(AIOperationRun.provider, AIOperationRun.model))
        return [{"provider": p, "model": m, "runs": n, "latency_ms": float(latency or 0), "prompt_tokens": tokens_in or 0, "completion_tokens": tokens_out or 0, "estimated_cost_usd": float(cost or 0), "errors": errors or 0} for p, m, n, latency, tokens_in, tokens_out, cost, errors in rows]


@router.get("/quality/policies")
async def list_quality_policies(request: Request) -> list[dict[str, Any]]:
    async with request.app.state.session_factory() as session:
        return [{"id": str(row.id), "operation": row.operation, "minimum_score": row.minimum_score, "canary_percent": row.canary_percent, "budget_usd": row.budget_usd} for row in (await session.execute(select(AIQualityPolicy))).scalars()]


@router.put("/quality/policies/{operation}")
async def set_quality_policy(operation: str, payload: QualityPolicyInput, request: Request) -> dict[str, Any]:
    if operation != payload.operation: raise HTTPException(422, "operation mismatch")
    async with request.app.state.session_factory() as session, session.begin():
        row = await session.scalar(select(AIQualityPolicy).where(AIQualityPolicy.operation == operation))
        if row is None: row = AIQualityPolicy(operation=operation); session.add(row)
        row.minimum_score, row.canary_percent, row.budget_usd = payload.minimum_score, payload.canary_percent, payload.budget_usd
        return {"operation": row.operation, "minimum_score": row.minimum_score, "canary_percent": row.canary_percent, "budget_usd": row.budget_usd, "audit": "policy_updated"}


@router.post("/quality/eval-sets")
async def freeze_eval_set(payload: EvalSetInput, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session, session.begin():
        row = AIEvalSet(operation=payload.operation, version=payload.version, cases=payload.cases, frozen=True)
        session.add(row); await session.flush()
        return {"id": str(row.id), "operation": row.operation, "version": row.version, "frozen": True}


@router.post("/quality/releases")
async def create_release(payload: ReleaseInput, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session, session.begin():
        if await session.get(PromptVersion, payload.prompt_version_id) is None: raise HTTPException(404, "prompt version not found")
        row = AIConfigRelease(prompt_version_id=payload.prompt_version_id, provider=payload.provider, model=payload.model, audit={"operation": payload.operation, "action": "created"})
        session.add(row); await session.flush(); await promote(session, row, payload.eval_score)
        return {"id": str(row.id), "status": row.status, "rollout_percent": row.rollout_percent, "eval_score": row.eval_score, "audit": row.audit}


@router.post("/quality/releases/{release_id}/rollback")
async def rollback_release(release_id: UUID, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session, session.begin():
        row = await session.get(AIConfigRelease, release_id)
        if row is None: raise HTTPException(404, "release not found")
        await rollback(session, row); row.audit = {**row.audit, "action": "rollback"}
        return {"id": str(row.id), "status": row.status, "audit": row.audit}


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    parent_slug: str | None = None
    keywords: list[str] = Field(default_factory=list)


class TopicInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str | None = Field(default=None, max_length=2000)
    categories: list[CategoryInput] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    priority: int = 0
    relevance_threshold: float = Field(default=0.5, ge=0, le=1)
    additional_rules: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class TopicOutput(TopicInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class PromptInput(BaseModel):
    operation: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    description: str | None = Field(default=None, max_length=1000)
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    output_schema: str = Field(min_length=1, max_length=128)


class PromptVersionInput(BaseModel):
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    output_schema: str = Field(min_length=1, max_length=128)


class QualityPolicyInput(BaseModel):
    operation: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    minimum_score: float = Field(ge=0, le=1)
    canary_percent: int = Field(ge=1, le=100)
    budget_usd: float = Field(ge=0)


class EvalSetInput(BaseModel):
    operation: str
    version: int = Field(ge=1)
    cases: list[dict[str, Any]] = Field(min_length=1)


class ReleaseInput(BaseModel):
    prompt_version_id: UUID
    provider: str
    model: str
    operation: str
    eval_score: float = Field(ge=0, le=1)


class PromptOutput(BaseModel):
    template_id: UUID
    operation: str
    active_version_id: UUID
    active_version: int
    output_schema: str


class LanguageInput(BaseModel):
    code: str = Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    name: str = Field(min_length=1, max_length=128)
    direction: str = Field(pattern=r"^(ltr|rtl)$")
    priority: int = 0
    is_active: bool = True
    translation_enabled: bool = False


class LanguageOutput(LanguageInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class TerminologyInput(BaseModel):
    source_language_code: str = Field(min_length=2, max_length=16)
    target_language_code: str = Field(min_length=2, max_length=16)
    source_term: str = Field(min_length=1, max_length=512)
    target_term: str = Field(min_length=1, max_length=512)
    notes: str | None = Field(default=None, max_length=1000)
    is_active: bool = True


class TerminologyOutput(TerminologyInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


def _topic_values(payload: TopicInput) -> dict[str, Any]:
    values = payload.model_dump()
    values["categories"] = [category.model_dump() for category in payload.categories]
    return values


def _topic_output(topic: Topic) -> TopicOutput:
    return TopicOutput.model_validate(topic)


@router.post("/topics", response_model=TopicOutput, status_code=201)
async def create_topic(payload: TopicInput, request: Request) -> TopicOutput:
    _validate_categories(payload.categories)
    async with request.app.state.session_factory() as session:
        topic = Topic(**_topic_values(payload))
        session.add(topic)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(409, "topic slug already exists") from exc
        logger.info("ai_topic_created", topic_id=str(topic.id))
        return _topic_output(topic)


@router.get("/topics", response_model=list[TopicOutput])
async def list_topics(request: Request, active_only: bool = False) -> list[TopicOutput]:
    async with request.app.state.session_factory() as session:
        statement = select(Topic).order_by(Topic.priority.desc(), Topic.name)
        if active_only:
            statement = statement.where(Topic.is_active)
        topics = (await session.execute(statement)).scalars().all()
        return [_topic_output(topic) for topic in topics]


@router.put("/topics/{topic_id}", response_model=TopicOutput)
async def replace_topic(topic_id: UUID, payload: TopicInput, request: Request) -> TopicOutput:
    _validate_categories(payload.categories)
    async with request.app.state.session_factory() as session:
        topic = await session.get(Topic, topic_id)
        if topic is None:
            raise HTTPException(404, "topic not found")
        for name, value in _topic_values(payload).items():
            setattr(topic, name, value)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(409, "topic slug already exists") from exc
        logger.info("ai_topic_updated", topic_id=str(topic.id))
        return _topic_output(topic)


@router.delete("/topics/{topic_id}", status_code=204)
async def deactivate_topic(topic_id: UUID, request: Request) -> Response:
    async with request.app.state.session_factory() as session:
        topic = await session.get(Topic, topic_id)
        if topic is None:
            raise HTTPException(404, "topic not found")
        topic.is_active = False
        await session.commit()
        logger.info("ai_topic_deactivated", topic_id=str(topic.id))
    return Response(status_code=204)


@router.post("/prompts", response_model=PromptOutput, status_code=201)
async def create_prompt(payload: PromptInput, request: Request) -> PromptOutput:
    async with request.app.state.session_factory() as session, session.begin():
        template = PromptTemplate(operation=payload.operation, description=payload.description)
        session.add(template)
        await session.flush()
        version = PromptVersion(
            template_id=template.id,
            version=1,
            system_prompt=payload.system_prompt,
            user_prompt=payload.user_prompt,
            output_schema=payload.output_schema,
            is_active=True,
        )
        session.add(version)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "prompt operation already exists") from exc
        logger.info(
            "ai_prompt_created",
            prompt_template_id=str(template.id),
            prompt_version_id=str(version.id),
            operation=template.operation,
        )
        return PromptOutput(
            template_id=template.id,
            operation=template.operation,
            active_version_id=version.id,
            active_version=version.version,
            output_schema=version.output_schema,
        )


@router.post("/prompts/{template_id}/versions", response_model=PromptOutput, status_code=201)
async def create_prompt_version(
    template_id: UUID, payload: PromptVersionInput, request: Request
) -> PromptOutput:
    async with request.app.state.session_factory() as session, session.begin():
        template = await session.get(PromptTemplate, template_id)
        if template is None:
            raise HTTPException(404, "prompt template not found")
        latest = await session.scalar(
            select(func.max(PromptVersion.version)).where(PromptVersion.template_id == template.id)
        )
        await session.execute(
            update(PromptVersion)
            .where(PromptVersion.template_id == template.id)
            .values(is_active=False)
        )
        version = PromptVersion(
            template_id=template.id,
            version=int(latest or 0) + 1,
            system_prompt=payload.system_prompt,
            user_prompt=payload.user_prompt,
            output_schema=payload.output_schema,
            is_active=True,
        )
        session.add(version)
        await session.flush()
        logger.info(
            "ai_prompt_version_created",
            prompt_template_id=str(template.id),
            prompt_version_id=str(version.id),
            operation=template.operation,
            version=version.version,
        )
        return PromptOutput(
            template_id=template.id,
            operation=template.operation,
            active_version_id=version.id,
            active_version=version.version,
            output_schema=version.output_schema,
        )


@router.get("/prompts", response_model=list[PromptOutput])
async def list_prompts(request: Request) -> list[PromptOutput]:
    async with request.app.state.session_factory() as session:
        rows = (
            await session.execute(
                select(PromptTemplate, PromptVersion)
                .join(PromptVersion, PromptVersion.template_id == PromptTemplate.id)
                .where(PromptVersion.is_active)
                .order_by(PromptTemplate.operation)
            )
        ).all()
        return [
            PromptOutput(
                template_id=template.id,
                operation=template.operation,
                active_version_id=version.id,
                active_version=version.version,
                output_schema=version.output_schema,
            )
            for template, version in rows
        ]


def _validate_categories(categories: list[CategoryInput]) -> None:
    slugs = {category.slug for category in categories}
    if len(slugs) != len(categories):
        raise HTTPException(422, "category slugs must be unique")
    if any(category.parent_slug and category.parent_slug not in slugs for category in categories):
        raise HTTPException(422, "parent category must be part of the same topic")


@router.get("/languages", response_model=list[LanguageOutput])
async def list_languages(request: Request) -> list[LanguageOutput]:
    async with request.app.state.session_factory() as session:
        rows = (
            await session.execute(
                select(LanguageConfig).order_by(LanguageConfig.priority.desc(), LanguageConfig.code)
            )
        ).scalars()
        return [LanguageOutput.model_validate(row) for row in rows]


@router.post("/languages", response_model=LanguageOutput, status_code=201)
async def create_language(payload: LanguageInput, request: Request) -> LanguageOutput:
    async with request.app.state.session_factory() as session:
        language = LanguageConfig(**payload.model_dump())
        session.add(language)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(409, "language code already exists") from exc
        logger.info("ai_language_created", language_id=str(language.id), code=language.code)
        return LanguageOutput.model_validate(language)


@router.put("/languages/{code}", response_model=LanguageOutput)
async def update_language(code: str, payload: LanguageInput, request: Request) -> LanguageOutput:
    if payload.code != code:
        raise HTTPException(422, "language code cannot be changed")
    async with request.app.state.session_factory() as session:
        language = (
            await session.execute(select(LanguageConfig).where(LanguageConfig.code == code))
        ).scalar_one_or_none()
        if language is None:
            raise HTTPException(404, "language not found")
        for name, value in payload.model_dump().items():
            setattr(language, name, value)
        await session.commit()
        logger.info("ai_language_updated", language_id=str(language.id), code=language.code)
        return LanguageOutput.model_validate(language)


@router.get("/terminology", response_model=list[TerminologyOutput])
async def list_terminology(
    request: Request, source_language: str | None = None, target_language: str | None = None
) -> list[TerminologyOutput]:
    async with request.app.state.session_factory() as session:
        statement = select(TerminologyEntry).order_by(TerminologyEntry.created_at)
        if source_language:
            statement = statement.where(TerminologyEntry.source_language_code == source_language)
        if target_language:
            statement = statement.where(TerminologyEntry.target_language_code == target_language)
        rows = (await session.execute(statement)).scalars()
        return [TerminologyOutput.model_validate(row) for row in rows]


@router.post("/terminology", response_model=TerminologyOutput, status_code=201)
async def create_terminology(payload: TerminologyInput, request: Request) -> TerminologyOutput:
    async with request.app.state.session_factory() as session:
        await _ensure_languages_exist(
            session, payload.source_language_code, payload.target_language_code
        )
        entry = TerminologyEntry(**payload.model_dump())
        session.add(entry)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(409, "terminology entry already exists") from exc
        logger.info(
            "ai_terminology_created",
            terminology_id=str(entry.id),
            source_language=entry.source_language_code,
            target_language=entry.target_language_code,
        )
        return TerminologyOutput.model_validate(entry)


@router.put("/terminology/{entry_id}", response_model=TerminologyOutput)
async def update_terminology(
    entry_id: UUID, payload: TerminologyInput, request: Request
) -> TerminologyOutput:
    async with request.app.state.session_factory() as session:
        entry = await session.get(TerminologyEntry, entry_id)
        if entry is None:
            raise HTTPException(404, "terminology entry not found")
        await _ensure_languages_exist(
            session, payload.source_language_code, payload.target_language_code
        )
        for name, value in payload.model_dump().items():
            setattr(entry, name, value)
        await session.commit()
        logger.info("ai_terminology_updated", terminology_id=str(entry.id))
        return TerminologyOutput.model_validate(entry)


@router.delete("/terminology/{entry_id}", status_code=204)
async def deactivate_terminology(entry_id: UUID, request: Request) -> Response:
    async with request.app.state.session_factory() as session:
        entry = await session.get(TerminologyEntry, entry_id)
        if entry is None:
            raise HTTPException(404, "terminology entry not found")
        entry.is_active = False
        await session.commit()
        logger.info("ai_terminology_deactivated", terminology_id=str(entry.id))
    return Response(status_code=204)


async def _ensure_languages_exist(session: AsyncSession, source: str, target: str) -> None:
    if source == target:
        raise HTTPException(422, "source and target languages must differ")
    codes = set(
        (
            await session.execute(
                select(LanguageConfig.code).where(LanguageConfig.code.in_([source, target]))
            )
        ).scalars()
    )
    if codes != {source, target}:
        raise HTTPException(422, "source and target languages must exist")
