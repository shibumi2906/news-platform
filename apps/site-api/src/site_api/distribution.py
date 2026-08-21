"""Distribution channel administration and immutable job scheduling."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from common.logging import get_correlation_id, get_logger
from site_domain.distribution_capabilities import PROVIDER_CAPABILITIES, capabilities_for
from site_domain.models import (
    ArticleTranslationVersion,
    ArticleVersion,
    DistributionChannel,
    DistributionJob,
    MediaAsset,
    Publication,
    UnifiedJob,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

# A channel is only exposed to operators once its worker adapter is a real,
# supported integration.  The domain protocol remains provider-neutral, so a
# future adapter can be added without changing the scheduling model.
SUPPORTED_CHANNELS = frozenset(PROVIDER_CAPABILITIES)
SENSITIVE_CONFIG_FRAGMENTS = ("token", "secret", "password", "api_key", "credential")


def validate_channel_config(config: dict[str, Any]) -> None:
    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = key.lower().replace("-", "_")
                if any(fragment in normalized for fragment in SENSITIVE_CONFIG_FRAGMENTS):
                    raise ValueError("secrets must use credential_ref and environment storage")
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(config)


def _require_strings(config: dict[str, Any], *keys: str) -> None:
    missing = [key for key in keys if not isinstance(config.get(key), str) or not config[key]]
    if missing:
        raise ValueError(f"channel config requires: {', '.join(missing)}")


def validate_provider_config(kind: str, config: dict[str, Any]) -> None:
    validate_channel_config(config)
    requirements = {
        "telegram": ("chat_id",),
        "facebook": ("page_id",),
        "instagram": ("instagram_account_id", "media_url_template"),
        "tiktok": ("media_url_template",),
        "x": (),
        "youtube": ("channel_id", "media_url_template"),
    }
    _require_strings(config, *requirements[kind])
    for key in ("media_url_template", "article_url_template"):
        value = config.get(key)
        if value is not None and (not isinstance(value, str) or not value.startswith("https://")):
            raise ValueError(f"{key} must be an absolute https URL")
    template = config.get("media_url_template")
    if template is not None and "{asset_id}" not in template:
        raise ValueError("media_url_template must contain {asset_id}")


def _content(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("content")
    return nested if isinstance(nested, dict) else payload


async def create_channel(
    session: AsyncSession,
    *,
    name: str,
    kind: str,
    account_key: str,
    credential_ref: str | None,
    config: dict[str, Any],
) -> DistributionChannel:
    if kind not in SUPPORTED_CHANNELS:
        raise ValueError("unsupported distribution channel kind")
    validate_provider_config(kind, config)
    channel = DistributionChannel(
        name=name,
        kind=kind,
        account_key=account_key,
        credential_ref=credential_ref,
        config=config,
        is_active=True,
    )
    session.add(channel)
    await session.commit()
    logger.info("distribution_channel_created", channel_id=str(channel.id), channel_kind=kind)
    return channel


async def schedule_distribution(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    article_version_id: uuid.UUID,
    translation_version_id: uuid.UUID | None,
    media_asset_id: uuid.UUID | None,
    scheduled_at: datetime | None,
    idempotency_key: str | None,
    max_attempts: int,
) -> tuple[DistributionJob, bool]:
    channel = await session.get(DistributionChannel, channel_id)
    version = await session.get(ArticleVersion, article_version_id)
    if channel is None or version is None:
        raise LookupError("channel or article version not found")
    if not channel.is_active:
        raise ValueError("distribution channel is inactive")
    publication = (
        await session.execute(
            select(Publication).where(
                Publication.article_id == version.article_id,
                Publication.status == "published",
                Publication.active_article_version_id == article_version_id,
            )
        )
    ).scalar_one_or_none()
    if publication is None:
        raise ValueError("only the active published article version can be distributed")
    translation: ArticleTranslationVersion | None = None
    if translation_version_id is not None:
        translation = await session.get(ArticleTranslationVersion, translation_version_id)
        if translation is None or translation.article_version_id != article_version_id:
            raise ValueError("translation does not belong to article version")
    media: MediaAsset | None = None
    if media_asset_id is not None:
        asset = await session.get(MediaAsset, media_asset_id)
        if asset is None or asset.status != "ready":
            raise ValueError("media asset is not ready")
        media = asset
    content = translation.content if translation else _content(version.content)
    title = content.get("title") if isinstance(content.get("title"), str) else "News update"
    summary = content.get("summary") if isinstance(content.get("summary"), str) else ""
    body = content.get("body") if isinstance(content.get("body"), str) else ""
    locale = translation.language_code if translation else str(content.get("language", "und"))
    content_type = "text"
    if media is not None:
        content_type = "video" if media.mime_type.startswith("video/") else "image"
    elif isinstance(channel.config.get("article_url_template"), str):
        content_type = "link"
    capabilities = capabilities_for(channel.kind)
    if content_type not in capabilities.content_types:
        raise ValueError(f"{channel.kind} does not support {content_type} publication")
    if len(f"{title}\n\n{summary}") > capabilities.text_limit:
        raise ValueError(f"{channel.kind} text exceeds provider limit")
    media_url = None
    if media is not None:
        template = channel.config.get("media_url_template")
        if capabilities.requires_media_url and not isinstance(template, str):
            raise ValueError(f"{channel.kind} requires config.media_url_template for media")
        if isinstance(template, str):
            media_url = template.format(asset_id=media.id)
    article_url = None
    if isinstance(channel.config.get("article_url_template"), str):
        article_url = channel.config["article_url_template"].format(article_id=version.article_id)
    key = (
        idempotency_key
        or hashlib.sha256(
            f"{channel.kind}:{channel.account_key}:{article_version_id}:{translation_version_id}".encode()
        ).hexdigest()
    )
    existing = (
        await session.execute(select(DistributionJob).where(DistributionJob.idempotency_key == key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    due = scheduled_at or datetime.now(UTC)
    unified = UnifiedJob(
        queue="distribution",
        kind=f"publish:{channel.kind}",
        idempotency_key=key,
        status="scheduled",
        payload={
            "article_version_id": str(article_version_id),
            "channel_id": str(channel_id),
        },
        scheduled_at=due,
        next_attempt_at=due,
        attempt_count=0,
        max_attempts=max_attempts,
        correlation_id=get_correlation_id(),
    )
    session.add(unified)
    await session.flush()
    job = DistributionJob(
        unified_job_id=unified.id,
        channel_id=channel_id,
        article_version_id=article_version_id,
        translation_version_id=translation_version_id,
        media_asset_id=media_asset_id,
        idempotency_key=key,
        status="scheduled",
        scheduled_at=due,
        next_attempt_at=due,
        attempt_count=0,
        max_attempts=max_attempts,
        payload={
            "title": title,
            "summary": summary,
            "body": body,
            "locale": locale,
            "article_id": str(version.article_id),
            "article_version_id": str(version.id),
            "content_type": content_type,
            "media_url": media_url,
            "media_mime_type": media.mime_type if media else None,
            "article_url": article_url,
        },
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        winner = (
            await session.execute(
                select(DistributionJob).where(DistributionJob.idempotency_key == key)
            )
        ).scalar_one()
        return winner, False
    logger.info(
        "distribution_job_scheduled",
        job_id=str(job.id),
        channel_id=str(channel.id),
        channel_kind=channel.kind,
    )
    return job, True
