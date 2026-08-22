"""Generic async SQLAlchemy engine/session wiring.

Domain packages define their own tables on top of `Base`. This module
contains no domain tables — only the shared engine/session factory and a
minimal readiness probe (docs/02_SYSTEM_ARCHITECTURE.md §11 health checks).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import JSON, DateTime, Uuid, func, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from common.ids import new_uuid

_SELECT_ONE = text("SELECT 1")

#: Portable JSON column type: plain JSON everywhere, JSONB on Postgres.
#: Lets domain model tests run against SQLite while production runs Postgres.
PortableJSON = JSON().with_variant(postgresql.JSONB(), "postgresql")


class Base(DeclarativeBase):
    """Shared declarative base for every domain model."""


class UUIDPrimaryKeyMixin:
    """Dialect-agnostic UUID primary key (docs/00_GLOSSARY_AND_CONVENTIONS.md §4:
    every domain identifier is a UUID)."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)


class TimestampMixin:
    """`created_at`/`updated_at` required on every mutable entity
    (docs/04_DATA_MODEL.md §1)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(database_url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def ping(engine: AsyncEngine) -> bool:
    """Minimal readiness check: verify the database accepts a connection."""
    async with engine.connect() as connection:
        await connection.execute(_SELECT_ONE)
    return True
