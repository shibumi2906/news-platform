"""Incoming package (docs/04_DATA_MODEL.md §4, docs/14 §5).

`IncomingPackage` tracks the latest known version of a package delivered
by a connection. `IncomingPackageVersion` stores each delivered version's
payload immutably — a version row is never updated after insert.
"""

from __future__ import annotations

import uuid
from typing import Any

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class IncomingPackage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "incoming_package"
    __table_args__ = (
        UniqueConstraint("connection_id", "package_id", name="uq_incoming_package_connection"),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrator_connection.id"))
    package_id: Mapped[uuid.UUID]
    latest_version: Mapped[int] = mapped_column(Integer)


class IncomingPackageVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "incoming_package_version"
    __table_args__ = (
        UniqueConstraint(
            "incoming_package_id", "package_version", name="uq_incoming_package_version"
        ),
    )

    incoming_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incoming_package.id"))
    package_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
