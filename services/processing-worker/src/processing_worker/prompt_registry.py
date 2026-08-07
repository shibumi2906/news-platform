from __future__ import annotations

from integrator_domain.models import PromptTemplate, PromptVersion
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_active_prompt(session: AsyncSession, operation: str) -> PromptVersion:
    result = await session.execute(
        select(PromptVersion)
        .join(PromptTemplate, PromptTemplate.id == PromptVersion.template_id)
        .where(PromptTemplate.operation == operation, PromptVersion.is_active)
        .order_by(PromptVersion.version.desc())
        .limit(1)
    )
    prompt = result.scalar_one_or_none()
    if prompt is None:
        raise LookupError(f"active prompt not configured for operation: {operation}")
    return prompt
