"""AI Core outbox pipeline from SourceMaterial to versioned canonical draft package."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from common.hashing import sha256_hex
from common.logging import get_logger
from contracts.package import PackageContent
from integrator_domain.models import (
    AIOperationRun,
    CanonicalNewsPackage,
    DraftProvenance,
    Event,
    EventMatchReview,
    EventMaterial,
    ExtractedEntity,
    ExtractedFact,
    MaterialRelevance,
    OutboxEvent,
    PromptVersion,
    SourceMaterial,
    Topic,
    TranslationVersion,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from processing_worker.ai_gateway import (
    AIGateway,
    AIGatewayError,
    AIRequest,
    FakeAIProvider,
    GatewayResponse,
)
from processing_worker.event_intelligence import decide_cluster
from processing_worker.packaging import build_ai_package_envelope, envelope_to_row
from processing_worker.prompt_registry import get_active_prompt
from processing_worker.schemas import DraftOutput, ExtractionOutput, RelevanceOutput
from processing_worker.translation import TranslationPipelineError, generate_translations

SOURCE_MATERIAL_INGESTED = "source_material.ingested"
CANONICAL_PACKAGE_CREATED = "canonical_news_package.created"

logger = get_logger(__name__)


class _RecordedAIFailure(RuntimeError):
    pass


@dataclass
class ProcessingStats:
    processed: int = 0
    irrelevant: int = 0
    skipped_duplicate: int = 0
    failed: int = 0


async def process_pending_events(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    instance_id: UUID,
    batch_size: int,
    gateway: AIGateway | None = None,
) -> ProcessingStats:
    gateway = gateway or AIGateway([FakeAIProvider()])
    stats = ProcessingStats()
    async with session_factory() as session:
        pending_ids = list(
            (
                await session.execute(
                    select(OutboxEvent.id)
                    .where(
                        OutboxEvent.status == "pending",
                        OutboxEvent.event_type == SOURCE_MATERIAL_INGESTED,
                    )
                    .order_by(OutboxEvent.created_at)
                    .limit(batch_size)
                )
            ).scalars()
        )
    for outbox_event_id in pending_ids:
        outcome = await _process_one(
            session_factory, outbox_event_id, instance_id=instance_id, gateway=gateway
        )
        if outcome == "processed":
            stats.processed += 1
        elif outcome == "irrelevant":
            stats.irrelevant += 1
        elif outcome == "duplicate":
            stats.skipped_duplicate += 1
        else:
            stats.failed += 1
    return stats


async def _process_one(
    session_factory: async_sessionmaker[AsyncSession],
    outbox_event_id: UUID,
    *,
    instance_id: UUID,
    gateway: AIGateway,
) -> str:
    async with session_factory() as session:
        outbox = await session.get(OutboxEvent, outbox_event_id)
        if outbox is None or outbox.status != "pending":
            return "duplicate"
        try:
            material_id = UUID(outbox.payload["source_material_id"])
            stub_event_id = UUID(outbox.payload["event_id"])
        except (KeyError, ValueError, TypeError):
            return await _fail_outbox(session_factory, outbox_event_id, "invalid_outbox_payload")
        material = await session.get(SourceMaterial, material_id)
        stub_event = await session.get(Event, stub_event_id)
        already_processed = await session.scalar(
            select(MaterialRelevance.id).where(MaterialRelevance.source_material_id == material_id)
        )
        topics = list(
            (
                await session.execute(
                    select(Topic).where(Topic.is_active).order_by(Topic.priority.desc())
                )
            ).scalars()
        )
    if material is None or stub_event is None:
        return await _fail_outbox(session_factory, outbox_event_id, "processing_source_missing")
    if already_processed is not None:
        await _set_outbox_status(session_factory, outbox_event_id, "processed")
        return "duplicate"
    if not topics:
        return await _fail_outbox(session_factory, outbox_event_id, "active_topics_missing")

    active_prompt: PromptVersion | None = None
    active_operation = "relevance"
    active_input: dict[str, Any] = {}
    active_provider = "routing"
    active_model = "unknown"
    try:
        relevance_prompt = await _prompt(session_factory, "relevance")
        active_prompt = relevance_prompt
        active_input = {
            "text": f"{material.title}\n{material.excerpt or ''}\n{material.body or ''}",
            "topics": [_topic_payload(topic) for topic in topics],
        }
        relevance_response = await gateway.complete(
            AIRequest(
                operation="relevance",
                system_prompt=relevance_prompt.system_prompt,
                user_prompt=relevance_prompt.user_prompt,
                input_data=active_input,
            )
        )
        active_provider, active_model = relevance_response.provider, relevance_response.model
        relevance = RelevanceOutput.model_validate(relevance_response.output)
        relevance_run_id = await _store_run(
            session_factory, relevance_prompt, "relevance", active_input, relevance_response
        )
        await _store_relevance(
            session_factory,
            material.id,
            relevance_run_id,
            relevance,
            {topic.id for topic in topics},
        )
        relevant_matches = [match for match in relevance.matches if match.is_relevant]
        if not relevant_matches:
            await _set_outbox_status(session_factory, outbox_event_id, "processed")
            logger.info("ai_material_irrelevant", source_material_id=str(material.id))
            return "irrelevant"

        extraction_prompt = await _prompt(session_factory, "extraction")
        active_prompt = extraction_prompt
        active_operation = "extraction"
        active_input = {
            "title": material.title,
            "body": material.body or material.excerpt or "",
        }
        extraction_response = await gateway.complete(
            AIRequest(
                operation="extraction",
                system_prompt=extraction_prompt.system_prompt,
                user_prompt=extraction_prompt.user_prompt,
                input_data=active_input,
            )
        )
        active_provider, active_model = extraction_response.provider, extraction_response.model
        extraction = ExtractionOutput.model_validate(extraction_response.output)
        extraction_run_id = await _store_run(
            session_factory, extraction_prompt, "extraction", active_input, extraction_response
        )
        event_id, fact_ids = await _store_extraction_and_cluster(
            session_factory,
            material,
            stub_event_id,
            extraction_run_id,
            extraction,
        )
        await _create_event_draft(
            session_factory,
            event_id,
            instance_id,
            gateway,
            taxonomy=[
                value
                for match in relevant_matches
                for value in (
                    str(match.topic_id),
                    *([match.category_slug] if match.category_slug else []),
                )
            ],
            regions=[
                region
                for match in relevant_matches
                for topic in topics
                if topic.id == match.topic_id
                for region in topic.regions
            ],
        )
        await _set_outbox_status(session_factory, outbox_event_id, "processed")
        logger.info(
            "ai_material_processed",
            source_material_id=str(material.id),
            event_id=str(event_id),
            extracted_facts=len(fact_ids),
        )
        return "processed"
    except (
        AIGatewayError,
        LookupError,
        ValidationError,
        ValueError,
        _RecordedAIFailure,
        TranslationPipelineError,
    ) as exc:
        if isinstance(exc, AIGatewayError):
            active_provider, active_model = exc.provider, exc.model
        if active_prompt is not None and not isinstance(
            exc, (_RecordedAIFailure, TranslationPipelineError)
        ):
            await _store_failed_run(
                session_factory,
                active_prompt,
                active_operation,
                active_input,
                provider=active_provider,
                model=active_model,
                error_code=type(exc).__name__,
            )
        logger.error(
            "ai_material_processing_failed",
            source_material_id=str(material.id),
            error_type=type(exc).__name__,
        )
        return await _fail_outbox(session_factory, outbox_event_id, type(exc).__name__)


async def _prompt(
    session_factory: async_sessionmaker[AsyncSession], operation: str
) -> PromptVersion:
    async with session_factory() as session:
        return await get_active_prompt(session, operation)


def _topic_payload(topic: Topic) -> dict[str, Any]:
    return {
        "id": str(topic.id),
        "name": topic.name,
        "categories": topic.categories,
        "keywords": topic.keywords,
        "exclusions": topic.exclusions,
        "regions": topic.regions,
        "priority": topic.priority,
        "relevance_threshold": topic.relevance_threshold,
        "additional_rules": topic.additional_rules,
    }


async def _store_run(
    session_factory: async_sessionmaker[AsyncSession],
    prompt: PromptVersion,
    operation: str,
    input_data: dict[str, Any],
    response: GatewayResponse,
) -> UUID:
    serialized = json.dumps(input_data, sort_keys=True, ensure_ascii=False, default=str)
    async with session_factory() as session, session.begin():
        run = AIOperationRun(
            operation=operation,
            provider=response.provider,
            model=response.model,
            prompt_version_id=prompt.id,
            status="succeeded",
            input_hash=sha256_hex(serialized),
            output=response.output,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            estimated_cost_usd=response.estimated_cost_usd,
        )
        session.add(run)
        await session.flush()
        return run.id


async def _store_failed_run(
    session_factory: async_sessionmaker[AsyncSession],
    prompt: PromptVersion,
    operation: str,
    input_data: dict[str, Any],
    *,
    provider: str,
    model: str,
    error_code: str,
) -> None:
    serialized = json.dumps(input_data, sort_keys=True, ensure_ascii=False, default=str)
    async with session_factory() as session, session.begin():
        session.add(
            AIOperationRun(
                operation=operation,
                provider=provider,
                model=model,
                prompt_version_id=prompt.id,
                status="failed",
                input_hash=sha256_hex(serialized),
                error_code=error_code,
            )
        )


async def _store_relevance(
    session_factory: async_sessionmaker[AsyncSession],
    material_id: UUID,
    run_id: UUID,
    output: RelevanceOutput,
    configured_topics: set[UUID],
) -> None:
    returned_topics = {match.topic_id for match in output.matches}
    if not returned_topics.issubset(configured_topics):
        raise ValueError("provider returned an unknown topic")
    async with session_factory() as session, session.begin():
        for match in output.matches:
            session.add(
                MaterialRelevance(
                    source_material_id=material_id,
                    topic_id=match.topic_id,
                    category_slug=match.category_slug,
                    is_relevant=match.is_relevant,
                    score=match.score,
                    reason=match.reason,
                    ai_operation_run_id=run_id,
                )
            )


async def _store_extraction_and_cluster(
    session_factory: async_sessionmaker[AsyncSession],
    material: SourceMaterial,
    stub_event_id: UUID,
    run_id: UUID,
    output: ExtractionOutput,
) -> tuple[UUID, list[UUID]]:
    cluster_key = sha256_hex(output.event_key.casefold())
    async with session_factory() as session, session.begin():
        stub = await session.get(Event, stub_event_id)
        if stub is None:
            raise ValueError("event stub disappeared")
        decision = await decide_cluster(
            session,
            material,
            event_key=cluster_key,
            entity_names=[entity.name for entity in output.entities],
        )
        event = await session.get(Event, decision.event_id) if decision.event_id else None
        if decision.action == "auto_merge" and event is not None:
            stub.status = "merged"
            stub.merged_into_event_id = event.id
            event.cluster_confidence = max(event.cluster_confidence, decision.score)
        else:
            event = stub
            event.cluster_key = cluster_key
            event.title = material.title
            event.summary = material.excerpt
            event.cluster_confidence = decision.score if decision.score else 1.0
        exists = await session.scalar(
            select(EventMaterial.id).where(
                EventMaterial.event_id == event.id,
                EventMaterial.source_material_id == material.id,
            )
        )
        if exists is None:
            session.add(
                EventMaterial(
                    event_id=event.id,
                    source_material_id=material.id,
                    similarity_score=decision.score,
                    decision=decision.action,
                    evidence=decision.evidence,
                )
            )
        if decision.action == "review" and decision.event_id is not None:
            session.add(
                EventMatchReview(
                    source_material_id=material.id,
                    proposed_event_id=stub.id,
                    candidate_event_id=decision.event_id,
                    score=decision.score,
                    evidence=decision.evidence,
                )
            )
        fact_ids: list[UUID] = []
        for fact_output in output.facts:
            fact = ExtractedFact(
                source_material_id=material.id,
                statement=fact_output.statement,
                fact_type=fact_output.fact_type,
                value=fact_output.value,
                confidence=fact_output.confidence,
                ai_operation_run_id=run_id,
            )
            session.add(fact)
            await session.flush()
            fact_ids.append(fact.id)
        for entity_output in output.entities:
            session.add(
                ExtractedEntity(
                    source_material_id=material.id,
                    kind=entity_output.kind,
                    name=entity_output.name,
                    normalized_name=entity_output.name.casefold(),
                    confidence=entity_output.confidence,
                    ai_operation_run_id=run_id,
                )
            )
        return event.id, fact_ids


async def _create_event_draft(
    session_factory: async_sessionmaker[AsyncSession],
    event_id: UUID,
    instance_id: UUID,
    gateway: AIGateway,
    *,
    taxonomy: list[str],
    regions: list[str],
) -> None:
    async with session_factory() as session:
        event = await session.get(Event, event_id)
        if event is None:
            raise ValueError("cluster event missing")
        material_ids = list(
            (
                await session.execute(
                    select(EventMaterial.source_material_id).where(
                        EventMaterial.event_id == event.id
                    )
                )
            ).scalars()
        )
        materials = list(
            (
                await session.execute(
                    select(SourceMaterial)
                    .where(SourceMaterial.id.in_(material_ids))
                    .order_by(SourceMaterial.published_at)
                )
            ).scalars()
        )
        facts = list(
            (
                await session.execute(
                    select(ExtractedFact).where(ExtractedFact.source_material_id.in_(material_ids))
                )
            ).scalars()
        )
        entities = list(
            (
                await session.execute(
                    select(ExtractedEntity).where(
                        ExtractedEntity.source_material_id.in_(material_ids)
                    )
                )
            ).scalars()
        )
        previous = (
            await session.execute(
                select(CanonicalNewsPackage)
                .where(CanonicalNewsPackage.event_id == event.id)
                .order_by(CanonicalNewsPackage.package_version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    prompt = await _prompt(session_factory, "draft")
    draft_input = {
        "materials": [
            {"title": item.title, "excerpt": item.excerpt, "body": item.body} for item in materials
        ],
        "facts": [item.value for item in facts],
        "entities": [item.name for item in entities],
        "tags": list(dict.fromkeys([*taxonomy, *[item.name for item in entities]])),
    }
    try:
        response = await gateway.complete(
            AIRequest(
                operation="draft",
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_prompt,
                input_data=draft_input,
            )
        )
        draft = DraftOutput.model_validate(response.output)
    except (AIGatewayError, ValidationError) as exc:
        provider = exc.provider if isinstance(exc, AIGatewayError) else "routing"
        model = exc.model if isinstance(exc, AIGatewayError) else "unknown"
        await _store_failed_run(
            session_factory,
            prompt,
            "draft",
            draft_input,
            provider=provider,
            model=model,
            error_code=type(exc).__name__,
        )
        raise _RecordedAIFailure("draft operation failed") from exc
    await _store_run(session_factory, prompt, "draft", draft_input, response)
    translation_bundle = await generate_translations(session_factory, materials[0], draft, gateway)
    language_versions = {
        item.target_language_code: PackageContent(
            title=item.content.title,
            lead=item.content.lead,
            excerpt=item.content.summary,
            body=item.content.body,
            summary=item.content.summary,
            tags=item.content.tags,
            canonical_url=materials[0].canonical_url,
            language=item.target_language_code,
            direction="rtl" if item.direction == "rtl" else "ltr",
        )
        for item in translation_bundle.translations
    }
    package_id = previous.package_id if previous else uuid4()
    package_version = previous.package_version + 1 if previous else 1
    fact_payload = [
        {
            "id": str(item.id),
            "statement": item.statement,
            "type": item.fact_type,
            "value": item.value,
            "confidence": item.confidence,
            "source_material_id": str(item.source_material_id),
        }
        for item in facts
    ]
    entity_payload = [
        {
            "id": str(item.id),
            "kind": item.kind,
            "name": item.name,
            "confidence": item.confidence,
            "source_material_id": str(item.source_material_id),
        }
        for item in entities
    ]
    envelope = build_ai_package_envelope(
        materials,
        event,
        draft,
        instance_id=instance_id,
        package_id=package_id,
        package_version=package_version,
        facts=fact_payload,
        entities=entity_payload,
        taxonomy=list(dict.fromkeys(taxonomy)),
        regions=list(dict.fromkeys(regions)),
        source_language=translation_bundle.source_language_code,
        source_direction=translation_bundle.source_direction,
        language_versions=language_versions,
    )
    async with session_factory() as session, session.begin():
        package = envelope_to_row(envelope)
        session.add(package)
        await session.flush()
        for item in translation_bundle.translations:
            session.add(
                TranslationVersion(
                    package_row_id=package.id,
                    source_language_code=translation_bundle.source_language_code,
                    target_language_code=item.target_language_code,
                    direction=item.direction,
                    content=item.content.model_dump(mode="json"),
                    terminology_revision=item.terminology_revision,
                    ai_operation_run_id=item.ai_operation_run_id,
                )
            )
        facts_by_material: dict[UUID, list[ExtractedFact]] = {}
        for fact in facts:
            facts_by_material.setdefault(fact.source_material_id, []).append(fact)
        for material in materials:
            material_facts = facts_by_material.get(material.id)
            if not material_facts:
                session.add(
                    DraftProvenance(
                        package_row_id=package.id,
                        source_material_id=material.id,
                        extracted_fact_id=None,
                    )
                )
                continue
            for fact in material_facts:
                session.add(
                    DraftProvenance(
                        package_row_id=package.id,
                        source_material_id=material.id,
                        extracted_fact_id=fact.id,
                    )
                )
        session.add(
            OutboxEvent(
                event_type=CANONICAL_PACKAGE_CREATED,
                payload={
                    "package_id": str(package.package_id),
                    "package_version": package.package_version,
                    "event_id": str(event.id),
                    "instance_id": str(instance_id),
                },
            )
        )


async def _set_outbox_status(
    session_factory: async_sessionmaker[AsyncSession], outbox_event_id: UUID, status: str
) -> None:
    async with session_factory() as session, session.begin():
        outbox = await session.get(OutboxEvent, outbox_event_id)
        if outbox is not None:
            outbox.status = status


async def _fail_outbox(
    session_factory: async_sessionmaker[AsyncSession], outbox_event_id: UUID, error_code: str
) -> str:
    await _set_outbox_status(session_factory, outbox_event_id, "failed")
    logger.error("ai_outbox_failed", outbox_event_id=str(outbox_event_id), error_code=error_code)
    return "failed"
