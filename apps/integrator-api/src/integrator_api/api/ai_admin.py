from __future__ import annotations

from typing import Any
from uuid import UUID

from common.logging import get_logger
from fastapi import APIRouter, HTTPException, Request, Response
from integrator_domain.models import PromptTemplate, PromptVersion, Topic
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/api/v1/ai", tags=["ai-admin"])
logger = get_logger(__name__)


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


class PromptOutput(BaseModel):
    template_id: UUID
    operation: str
    active_version_id: UUID
    active_version: int
    output_schema: str


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
