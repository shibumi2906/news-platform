"""Deterministic content hashing.

Used wherever a stable digest of a string is needed for dedup or integrity
checks — e.g. `source_material.canonical_url_hash`
(docs/04_DATA_MODEL.md §3) and `ingestion_attempt.request_body_hash`.
"""

from __future__ import annotations

import hashlib


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
