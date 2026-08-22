"""UUID helpers.

All external and primary domain identifiers are UUIDs
(docs/00_GLOSSARY_AND_CONVENTIONS.md §4). Identifiers are never reused.
"""

from __future__ import annotations

import uuid


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def new_uuid_str() -> str:
    return str(uuid.uuid4())
