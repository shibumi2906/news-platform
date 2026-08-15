from __future__ import annotations
# ruff: noqa

import pytest

from source_worker.parser_platform import (
    SandboxViolation,
    detect_drift,
    run_snapshot_sandbox,
    suggest_rules,
    validate_egress_url,
    validate_rules,
)

FIXTURE = "<main><article><a href='/one'><h1>One</h1></a><div class='content'>Body</div></article></main>"
RULES = {"item_selector": "article", "url_selector": "a", "title_selector": "h1", "content_selector": ".content"}


async def test_snapshot_sandbox_accepts_valid_rules_and_detects_drift() -> None:
    result = await run_snapshot_sandbox(FIXTURE, RULES)
    assert result.ok and result.report["valid_items"] == 1
    assert detect_drift("<main><section>changed</section></main>", RULES)["reason"] == "item_selector_no_longer_matches"  # type: ignore[index]


async def test_successful_and_unsuccessful_repair_suggestions_are_reproducible() -> None:
    rules = suggest_rules(FIXTURE)
    assert (await run_snapshot_sandbox(FIXTURE, rules)).ok
    assert not (await run_snapshot_sandbox("<body>empty</body>", RULES)).ok


def test_sandbox_rejects_ssrf_code_and_oversized_rules() -> None:
    for unsafe in ("http://127.0.0.1/admin", "http://[::1]/", "file:///etc/passwd", "http://metadata.google.internal/"):
        with pytest.raises(SandboxViolation):
            validate_egress_url(unsafe)
    with pytest.raises(SandboxViolation):
        validate_rules({**RULES, "code": "import os"})
    with pytest.raises(SandboxViolation):
        validate_rules({**RULES, "item_selector": "a" * 300})


async def test_sandbox_enforces_fixture_resource_limit() -> None:
    with pytest.raises(SandboxViolation, match="memory limit"):
        await run_snapshot_sandbox("x" * 1_000_001, RULES)
