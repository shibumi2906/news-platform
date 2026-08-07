"""Application services for stored media, generation, memes, and video briefs."""

from __future__ import annotations

import hashlib
import html
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from common.logging import get_logger
from site_domain.models import (
    ArticleMediaLink,
    ArticleTranslationVersion,
    ArticleVersion,
    MediaAsset,
    MediaGenerationRun,
    MemeTemplate,
    MemeVersion,
    VideoProject,
)
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from site_api.media_generation import MediaGateway, MediaModerationError, MediaProviderError
from site_api.storage import ObjectStorage

logger = get_logger(__name__)


@dataclass(frozen=True)
class AssetInput:
    data: bytes
    mime_type: str
    kind: str
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    source_event_id: uuid.UUID | None = None
    source_url: str | None = None
    provenance: dict[str, Any] | None = None
    rights: dict[str, Any] | None = None
    ai_generated: bool = False
    parent_asset_id: uuid.UUID | None = None


async def store_asset(
    session: AsyncSession, storage: ObjectStorage, item: AssetInput
) -> MediaAsset:
    digest = hashlib.sha256(item.data).hexdigest()
    asset = MediaAsset(
        bucket=storage.bucket,
        object_key=f"assets/{digest[:2]}/{uuid.uuid4()}-{digest[:12]}",
        storage_provider="s3",
        kind=item.kind,
        status="pending",
        mime_type=item.mime_type,
        size_bytes=len(item.data),
        checksum_sha256=digest,
        width=item.width,
        height=item.height,
        duration_ms=item.duration_ms,
        source_event_id=item.source_event_id,
        source_url=item.source_url,
        provenance=item.provenance or {},
        rights=item.rights or {},
        ai_generated=item.ai_generated,
        parent_asset_id=item.parent_asset_id,
    )
    session.add(asset)
    await session.flush()
    try:
        await storage.put(asset.object_key, item.data, item.mime_type)
    except Exception:
        asset.status = "failed"
        await session.commit()
        logger.exception("media_storage_write_failed", asset_id=str(asset.id))
        raise
    asset.status = "ready"
    await session.commit()
    logger.info("media_asset_stored", asset_id=str(asset.id), kind=asset.kind)
    return asset


def article_prompt(version: ArticleVersion) -> str:
    content = version.content.get("content", version.content)
    title = content.get("title", "") if isinstance(content, dict) else ""
    summary = content.get("summary", "") if isinstance(content, dict) else ""
    return f"Editorial news illustration. Title: {title}. Summary: {summary}. No text or logos."


async def generate_article_images(
    session: AsyncSession,
    storage: ObjectStorage,
    gateway: MediaGateway,
    *,
    article_version_id: uuid.UUID,
    variants: int,
) -> tuple[MediaGenerationRun, list[MediaAsset]]:
    version = await session.get(ArticleVersion, article_version_id)
    if version is None:
        raise LookupError("article version not found")
    prompt = article_prompt(version)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    run = MediaGenerationRun(
        article_version_id=article_version_id,
        operation="image_generation",
        provider="pending",
        model="pending",
        status="running",
        prompt_hash=prompt_hash,
        variant_count=variants,
        estimated_cost_usd=Decimal("0"),
    )
    session.add(run)
    await session.flush()
    try:
        result = await gateway.generate(prompt, variants)
    except MediaModerationError as exc:
        run.status = "moderated"
        run.error_code = exc.code
        await session.commit()
        logger.warning("media_generation_moderated", run_id=str(run.id))
        raise
    except MediaProviderError as exc:
        run.status = "failed"
        run.error_code = exc.code
        await session.commit()
        logger.error("media_generation_failed", run_id=str(run.id), error_code=exc.code)
        raise
    run.provider = result.provider
    run.model = result.model
    run.input_tokens = result.input_tokens
    run.output_tokens = result.output_tokens
    run.estimated_cost_usd = result.estimated_cost_usd
    run.latency_ms = result.latency_ms
    run.moderation = result.moderation
    assets: list[MediaAsset] = []
    try:
        for index, generated in enumerate(result.items):
            asset = await store_asset(
                session,
                storage,
                AssetInput(
                    data=generated.data,
                    mime_type=generated.mime_type,
                    kind="generated_image",
                    width=generated.width,
                    height=generated.height,
                    ai_generated=True,
                    provenance={
                        "generation_run_id": str(run.id),
                        "variant_index": index,
                        "provider": result.provider,
                        "model": result.model,
                    },
                    rights={
                        "allowed_uses": ["editorial", "distribution"],
                        "ai_generated": True,
                    },
                ),
            )
            session.add(
                ArticleMediaLink(
                    media_asset_id=asset.id,
                    article_version_id=article_version_id,
                    role="candidate",
                    selected=False,
                    sort_order=index,
                )
            )
            assets.append(asset)
    except Exception:
        run.status = "failed"
        run.error_code = "storage_write_failed"
        await session.commit()
        raise
    run.status = "succeeded"
    await session.commit()
    logger.info(
        "media_generation_succeeded",
        run_id=str(run.id),
        provider=result.provider,
        model=result.model,
        variant_count=len(assets),
        latency_ms=result.latency_ms,
        estimated_cost_usd=str(result.estimated_cost_usd),
    )
    return run, assets


async def select_media(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID,
    article_version_id: uuid.UUID,
    translation_version_id: uuid.UUID | None,
    role: str,
) -> ArticleMediaLink:
    if await session.get(MediaAsset, asset_id) is None:
        raise LookupError("media asset not found")
    if await session.get(ArticleVersion, article_version_id) is None:
        raise LookupError("article version not found")
    if translation_version_id is not None:
        translation = await session.get(ArticleTranslationVersion, translation_version_id)
        if translation is None or translation.article_version_id != article_version_id:
            raise ValueError("translation does not belong to article version")
    await session.execute(
        update(ArticleMediaLink)
        .where(
            ArticleMediaLink.article_version_id == article_version_id,
            ArticleMediaLink.translation_version_id == translation_version_id,
            ArticleMediaLink.role == role,
        )
        .values(selected=False)
    )
    link = (
        await session.execute(
            select(ArticleMediaLink).where(
                ArticleMediaLink.media_asset_id == asset_id,
                ArticleMediaLink.article_version_id == article_version_id,
                ArticleMediaLink.translation_version_id == translation_version_id,
                ArticleMediaLink.role == role,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        link = ArticleMediaLink(
            media_asset_id=asset_id,
            article_version_id=article_version_id,
            translation_version_id=translation_version_id,
            role=role,
            selected=True,
        )
        session.add(link)
    else:
        link.selected = True
    await session.commit()
    logger.info(
        "media_selected", asset_id=str(asset_id), article_version_id=str(article_version_id)
    )
    return link


async def create_meme(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    template_id: uuid.UUID,
    article_version_id: uuid.UUID,
    mode: str,
    caption: str | None,
) -> MemeVersion:
    template = await session.get(MemeTemplate, template_id)
    version = await session.get(ArticleVersion, article_version_id)
    if template is None or version is None:
        raise LookupError("template or article version not found")
    if mode == "ai":
        content = version.content.get("content", version.content)
        title = content.get("title", "News") if isinstance(content, dict) else "News"
        caption = f"When the headline lands: {title}"
    if not caption:
        raise ValueError("caption is required")
    safe_caption = html.escape(caption[:280])
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='1080' height='1080'>"
        "<rect width='1080' height='1080' fill='#111827'/><text x='60' y='900' "
        f"fill='white' font-size='44'>{safe_caption}</text></svg>"
    ).encode()
    asset = await store_asset(
        session,
        storage,
        AssetInput(
            data=svg,
            mime_type="image/svg+xml",
            kind="meme",
            width=1080,
            height=1080,
            ai_generated=mode == "ai",
            parent_asset_id=template.base_asset_id,
            provenance={"template_id": str(template.id), "caption_mode": mode},
            rights={"allowed_uses": ["editorial", "distribution"]},
        ),
    )
    number = (
        await session.scalar(
            select(func.count(MemeVersion.id)).where(MemeVersion.template_id == template_id)
        )
        or 0
    ) + 1
    meme = MemeVersion(
        template_id=template_id,
        article_version_id=article_version_id,
        output_asset_id=asset.id,
        version_number=number,
        mode=mode,
        caption=caption,
        provenance={"template_id": str(template.id), "source_article_version_id": str(version.id)},
    )
    session.add(meme)
    await session.commit()
    logger.info("meme_version_created", meme_version_id=str(meme.id), mode=mode)
    return meme


async def create_video_project(
    session: AsyncSession, *, article_version_id: uuid.UUID
) -> VideoProject:
    version = await session.get(ArticleVersion, article_version_id)
    if version is None:
        raise LookupError("article version not found")
    content = version.content.get("content", version.content)
    title = str(content.get("title", "News update")) if isinstance(content, dict) else "News update"
    summary = str(content.get("summary", "")) if isinstance(content, dict) else ""
    scenes = [
        {"number": 1, "duration_seconds": 3, "visual": "Opening title card"},
        {"number": 2, "duration_seconds": 8, "visual": "Key event illustration"},
        {"number": 3, "duration_seconds": 4, "visual": "Source and follow-up card"},
    ]
    project = VideoProject(
        article_version_id=article_version_id,
        status="ready",
        script=f"{title}. {summary}".strip(),
        storyboard=scenes,
        provider="fake",
        model="fake-storyboard-v1",
        telemetry={"input_tokens": max(1, (len(title) + len(summary)) // 4), "cost_usd": "0"},
    )
    session.add(project)
    await session.commit()
    logger.info("video_project_created", project_id=str(project.id), scene_count=len(scenes))
    return project
