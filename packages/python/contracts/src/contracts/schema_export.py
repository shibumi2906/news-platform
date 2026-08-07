"""Regenerates the JSON Schema artifact for the canonical news package envelope.

docs/14_PUBLIC_AND_INTERNAL_API.md §4: "Schema публикуется как отдельный JSON
Schema artifact." Run with `uv run python -m contracts.schema_export` after
changing `contracts.package.CanonicalNewsPackageEnvelope`.
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.package import CanonicalNewsPackageEnvelope

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "canonical_news_package.schema.json"


def export_schema() -> str:
    return json.dumps(CanonicalNewsPackageEnvelope.model_json_schema(), indent=2, sort_keys=True)


def main() -> None:
    SCHEMA_PATH.write_text(export_schema() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
