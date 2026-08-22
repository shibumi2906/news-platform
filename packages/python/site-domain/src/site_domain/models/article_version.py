"""Article version and its source links (docs/04_DATA_MODEL.md §4, §10 EDITORIAL_WORKFLOW §3).

`ArticleVersion` is an immutable snapshot of editorial content: once
inserted it is never updated. `ArticleSourceLink` records which
`incoming_package` (and, optionally, up to which delivered version) a
given article draws from, so a later package version can be diffed against
what the editor already reviewed.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base, PortableJSON, TimestampMixin, UUIDPrimaryKeyMixin


class ArticleVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "article_version"
    __table_args__ = (
        UniqueConstraint("article_id", "version_number", name="uq_article_version_number"),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_article.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    #: Editorial content snapshot (title, body, facts, sources, language
    #: versions, rights) — shape mirrors the package envelope's `content`.
    content: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
    #: Temporary actor identity (`X-Actor-Id`) until real auth/RBAC exists.
    created_by_actor_id: Mapped[str] = mapped_column(String(255))
    #: The delivered package version this edit incorporated, if any — absent
    #: for purely manual edits with no new incoming data.
    based_on_incoming_package_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incoming_package_version.id"), default=None
    )


class ArticleSourceLink(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "article_source_link"
    __table_args__ = (
        UniqueConstraint("article_id", "incoming_package_id", name="uq_article_source_link"),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_article.id"))
    incoming_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incoming_package.id"))
    #: Highest `incoming_package_version` the editor has already reviewed/merged.
    last_merged_package_version: Mapped[int] = mapped_column(Integer)
