"""Safe, fixture-driven parser lab shared by HTTP HTML and Playwright sources.

Only declarative selectors are executed.  Arbitrary parser code is deliberately
not an accepted artifact, so this runner has no DB, credential or network side
effects; callers must validate a URL before any live fetch.
"""
# ruff: noqa

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from source_worker.html import _first_attr, _first_text, _parse_document, select

MAX_HTML_BYTES = 1_000_000
MAX_RULE_BYTES = 32_000
MAX_SELECTOR_LENGTH = 256
REQUIRED_RULES = {"item_selector", "url_selector", "title_selector", "content_selector"}


class SandboxViolation(ValueError):
    pass


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    report: dict[str, object]


def validate_egress_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SandboxViolation("only absolute http(s) URLs are allowed")
    host = parsed.hostname.casefold().rstrip(".")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".local"):
        raise SandboxViolation("private or metadata hosts are forbidden")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise SandboxViolation("private, loopback, link-local and reserved addresses are forbidden")
    return url


def validate_rules(rules: Mapping[str, object]) -> dict[str, object]:
    if len(json.dumps(dict(rules), sort_keys=True)) > MAX_RULE_BYTES:
        raise SandboxViolation("parser rules exceed sandbox size limit")
    if "code" in rules or "script" in rules:
        raise SandboxViolation("executable parser code is not supported")
    missing = sorted(key for key in REQUIRED_RULES if not isinstance(rules.get(key), str) or not rules[key])
    if missing:
        raise SandboxViolation(f"missing required selector rules: {', '.join(missing)}")
    for key, value in rules.items():
        if key.endswith("_selector"):
            if not isinstance(value, str) or len(value) > MAX_SELECTOR_LENGTH:
                raise SandboxViolation(f"unsafe selector value for {key}")
            if any(token in value for token in ("<", ">", "{", "}", ";", ":", "\\")):
                raise SandboxViolation(f"unsupported selector syntax for {key}")
    return dict(rules)


async def run_snapshot_sandbox(html: str, rules: Mapping[str, object], *, timeout_seconds: float = 1.0) -> SandboxResult:
    """Bounded parser-rule evaluation with deterministic preview diagnostics."""
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise SandboxViolation("HTML fixture exceeds sandbox memory limit")
    safe_rules = validate_rules(rules)

    async def evaluate() -> SandboxResult:
        document = _parse_document(html.encode())
        items = select(document.root, str(safe_rules["item_selector"]))
        previews: list[dict[str, str]] = []
        valid = 0
        for item in items[:50]:
            title = _first_text(item, str(safe_rules["title_selector"]))
            url = _first_attr(item, str(safe_rules["url_selector"]), "href")
            content = _first_text(item, str(safe_rules["content_selector"]))
            if title and url:
                valid += 1
            previews.append({"title": title or "", "url": url or "", "content": content or ""})
        return SandboxResult(
            ok=valid > 0,
            report={"items": len(items), "valid_items": valid, "preview": previews[:3], "fixture_hash": hashlib.sha256(html.encode()).hexdigest()},
        )

    try:
        return await asyncio.wait_for(evaluate(), timeout=max(0.01, min(timeout_seconds, 5.0)))
    except TimeoutError as exc:
        raise SandboxViolation("parser sandbox timed out") from exc


def suggest_rules(html: str) -> dict[str, str]:
    """Conservative selector suggestions; humans must validate and approve them."""
    document = _parse_document(html.encode()[:MAX_HTML_BYTES])
    item_selector = "article" if select(document.root, "article") else ".article" if select(document.root, ".article") else "body"
    title_selector = "h1" if select(document.root, "h1") else "a" if select(document.root, "a") else "title"
    url_selector = "a" if select(document.root, "a") else "link"
    content_selector = "main" if select(document.root, "main") else ".content" if select(document.root, ".content") else "body"
    return {"item_selector": item_selector, "title_selector": title_selector, "url_selector": url_selector, "content_selector": content_selector, "canonical_selector": "link[rel=canonical]"}


def detect_drift(html: str, rules: Mapping[str, object]) -> dict[str, object] | None:
    """Return explainable drift evidence when an approved fixture no longer matches."""
    try:
        safe_rules = validate_rules(rules)
    except SandboxViolation as exc:
        return {"reason": "invalid_rules", "error": str(exc)}
    document = _parse_document(html.encode()[:MAX_HTML_BYTES])
    count = len(select(document.root, str(safe_rules["item_selector"])))
    if count == 0:
        return {"reason": "item_selector_no_longer_matches", "item_selector": safe_rules["item_selector"], "fixture_hash": hashlib.sha256(html.encode()).hexdigest()}
    return None


async def active_rules(session: object, source_id: object, fallback: Mapping[str, object]) -> dict[str, object]:
    """Resolve the sole approved version, preserving source runtime settings."""
    from integrator_domain.models import ParserVersion
    from sqlalchemy import select

    version = await session.scalar(select(ParserVersion).where(ParserVersion.source_id == source_id, ParserVersion.status == "active"))  # type: ignore[attr-defined]
    return {**dict(fallback), **(dict(version.rules) if version is not None else {})}
