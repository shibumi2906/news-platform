"""Language detection and glossary-aware translation through the shared AI Gateway."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from common.hashing import sha256_hex
from common.logging import get_logger
from integrator_domain.models import (
    AIOperationRun,
    LanguageConfig,
    MaterialLanguageDetection,
    PromptVersion,
    SourceMaterial,
    TerminologyEntry,
)
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from processing_worker.ai_gateway import AIGateway, AIGatewayError, AIRequest, GatewayResponse
from processing_worker.prompt_registry import get_active_prompt
from processing_worker.schemas import DraftOutput, LanguageDetectionOutput, TranslationOutput

logger = get_logger(__name__)


class TranslationPipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeneratedTranslation:
    target_language_code: str
    direction: str
    content: TranslationOutput
    terminology_revision: str
    ai_operation_run_id: UUID


@dataclass(frozen=True)
class TranslationBundle:
    source_language_code: str
    source_direction: str
    translations: list[GeneratedTranslation]


async def generate_translations(
    session_factory: async_sessionmaker[AsyncSession],
    material: SourceMaterial,
    draft: DraftOutput,
    gateway: AIGateway,
) -> TranslationBundle:
    async with session_factory() as session:
        languages = list(
            (
                await session.execute(
                    select(LanguageConfig)
                    .where(LanguageConfig.is_active)
                    .order_by(LanguageConfig.priority.desc())
                )
            ).scalars()
        )
    targets = [language for language in languages if language.translation_enabled]
    if not targets:
        source_direction = next(
            (item.direction for item in languages if item.code == material.language), "ltr"
        )
        return TranslationBundle(material.language, source_direction, [])

    async with session_factory() as session:
        existing_detection = (
            await session.execute(
                select(MaterialLanguageDetection).where(
                    MaterialLanguageDetection.source_material_id == material.id
                )
            )
        ).scalar_one_or_none()
    if existing_detection is None:
        detection_input = {
            "declared_language": material.language,
            "title": material.title,
            "body": material.body or material.excerpt or "",
        }
        detection, detection_run_id = await _call_operation(
            session_factory,
            gateway,
            "language_detection",
            detection_input,
            LanguageDetectionOutput,
        )
        if detection.language_code not in {language.code for language in languages}:
            logger.warning(
                "translation_language_not_configured",
                source_material_id=str(material.id),
                language_code=detection.language_code,
            )
            raise TranslationPipelineError("detected language is not configured")
        async with session_factory() as session, session.begin():
            session.add(
                MaterialLanguageDetection(
                    source_material_id=material.id,
                    language_code=detection.language_code,
                    confidence=detection.confidence,
                    ai_operation_run_id=detection_run_id,
                )
            )
    else:
        detection = LanguageDetectionOutput(
            language_code=existing_detection.language_code,
            confidence=existing_detection.confidence,
        )
    source_direction = next(
        (item.direction for item in languages if item.code == detection.language_code), "ltr"
    )
    generated: list[GeneratedTranslation] = []
    for target in targets:
        if target.code == detection.language_code:
            continue
        async with session_factory() as session:
            terminology = list(
                (
                    await session.execute(
                        select(TerminologyEntry).where(
                            TerminologyEntry.is_active,
                            TerminologyEntry.source_language_code == detection.language_code,
                            TerminologyEntry.target_language_code == target.code,
                        )
                    )
                ).scalars()
            )
        terms = [
            {
                "source_term": entry.source_term,
                "target_term": entry.target_term,
                "notes": entry.notes,
            }
            for entry in terminology
        ]
        revision = sha256_hex(
            json.dumps(
                [
                    {
                        "id": str(entry.id),
                        "updated_at": str(entry.updated_at),
                        "source_term": entry.source_term,
                        "target_term": entry.target_term,
                    }
                    for entry in terminology
                ],
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        translation_input = {
            "source_language": detection.language_code,
            "target_language": target.code,
            "direction": target.direction,
            "content": draft.model_dump(mode="json"),
            "terminology": terms,
        }
        output, run_id = await _call_operation(
            session_factory,
            gateway,
            "translation",
            translation_input,
            TranslationOutput,
        )
        generated.append(
            GeneratedTranslation(
                target_language_code=target.code,
                direction=target.direction,
                content=output,
                terminology_revision=revision,
                ai_operation_run_id=run_id,
            )
        )
        logger.info(
            "translation_completed",
            source_material_id=str(material.id),
            source_language=detection.language_code,
            target_language=target.code,
            direction=target.direction,
            terminology_entries=len(terms),
        )
    return TranslationBundle(detection.language_code, source_direction, generated)


async def _call_operation[T: BaseModel](
    session_factory: async_sessionmaker[AsyncSession],
    gateway: AIGateway,
    operation: str,
    input_data: dict[str, Any],
    output_model: type[T],
) -> tuple[T, UUID]:
    async with session_factory() as session:
        try:
            prompt = await get_active_prompt(session, operation)
        except LookupError as exc:
            raise TranslationPipelineError(str(exc)) from exc
    try:
        response = await gateway.complete(
            AIRequest(
                operation=operation,
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_prompt,
                input_data=input_data,
            )
        )
        output = output_model.model_validate(response.output)
    except (AIGatewayError, ValidationError) as exc:
        provider = exc.provider if isinstance(exc, AIGatewayError) else "routing"
        model = exc.model if isinstance(exc, AIGatewayError) else "unknown"
        await _store_failed_run(
            session_factory,
            prompt,
            operation,
            input_data,
            provider=provider,
            model=model,
            error_code=type(exc).__name__,
        )
        raise TranslationPipelineError(f"{operation} failed") from exc
    run_id = await _store_run(session_factory, prompt, operation, input_data, response)
    return output, run_id


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
            prompt_version_id=response.prompt_version_id or prompt.id,
            ai_config_release_id=response.release_id,
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
