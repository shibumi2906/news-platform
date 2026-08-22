"""Site Ingestion API response contract.

docs/02_SYSTEM_ARCHITECTURE.md §6.4 and docs/14_PUBLIC_AND_INTERNAL_API.md §5:
ingestion returns an unambiguous result and is idempotent per
`(connection_id, idempotency_key)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class IncomingPackageReceipt(BaseModel):
    package_id: UUID
    package_version: int
    status: Literal["accepted", "duplicate"]
    received_at: datetime
