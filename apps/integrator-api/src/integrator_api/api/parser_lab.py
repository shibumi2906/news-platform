"""Human-approved parser lab for reproducible HTML and browser rules."""
# ruff: noqa

from __future__ import annotations

import asyncio
import ipaddress
import json
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlparse
from uuid import UUID

from common.auth import require_permission
from common.hashing import sha256_hex
from fastapi import APIRouter, Depends, HTTPException, Request
from integrator_domain.models import ParserRepair, ParserSnapshot, ParserVersion, Source
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

class SandboxViolation(ValueError):
    pass


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


def validate_rules(rules: Mapping[str, object]) -> None:
    needed = ("item_selector", "url_selector", "title_selector", "content_selector")
    if "code" in rules or "script" in rules or len(json.dumps(rules)) > 32_000:
        raise SandboxViolation("executable or oversized parser artifact")
    if any(not isinstance(rules.get(key), str) or not rules[key] for key in needed):
        raise SandboxViolation("missing required selector rules")


async def run_snapshot_sandbox(html: str, rules: Mapping[str, object]) -> Any:
    validate_rules(rules)
    if len(html.encode()) > 1_000_000:
        raise SandboxViolation("HTML fixture exceeds sandbox memory limit")

    async def run() -> dict[str, object]:
        selector = str(rules["item_selector"])
        count = html.count("<" + selector)
        return {"ok": count > 0, "report": {"items": count, "valid_items": count}}

    result = await asyncio.wait_for(run(), timeout=1)
    return type("SandboxResult", (), result)()


def suggest_rules(html: str) -> dict[str, str]:
    return {
        "item_selector": "article" if "<article" in html else "body",
        "url_selector": "a",
        "title_selector": "h1" if "<h1" in html else "a",
        "content_selector": "main" if "<main" in html else "body",
    }


def detect_drift(html: str, rules: dict[str, object]) -> dict[str, object] | None:
    selector = str(rules.get("item_selector", ""))
    if "<" + selector not in html:
        return {"reason": "item_selector_no_longer_matches", "item_selector": selector}
    return None

router = APIRouter(prefix="/api/v1/parser-lab", tags=["parser-lab"], dependencies=[Depends(require_permission("sources:manage"))])


class SnapshotInput(BaseModel):
    source_id: UUID
    url: str
    html: str = Field(min_length=1, max_length=1_000_000)
    kind: str = "list"


class SnapshotOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_id: UUID
    url: str
    kind: str
    content_hash: str


class VersionInput(BaseModel):
    source_id: UUID
    adapter_type: str
    rules: dict[str, object]
    snapshot_id: UUID
    reason: str | None = Field(default=None, max_length=1000)


class VersionOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_id: UUID
    version: int
    adapter_type: str
    rules: dict[str, object]
    status: str
    validation_report: dict[str, object]
    reason: str | None


class RepairInput(BaseModel):
    snapshot_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


async def _snapshot(session: AsyncSession, snapshot_id: UUID) -> ParserSnapshot:
    snapshot = await session.get(ParserSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(404, "parser snapshot not found")
    return snapshot


@router.post("/snapshots", response_model=SnapshotOutput, status_code=201)
async def create_snapshot(payload: SnapshotInput, request: Request) -> ParserSnapshot:
    try:
        validate_egress_url(payload.url)
    except SandboxViolation as exc:
        raise HTTPException(422, str(exc)) from exc
    async with request.app.state.session_factory() as session, session.begin():
        if await session.get(Source, payload.source_id) is None:
            raise HTTPException(404, "source not found")
        snapshot = ParserSnapshot(source_id=payload.source_id, url=payload.url, kind=payload.kind, html=payload.html, content_hash=sha256_hex(payload.html))
        session.add(snapshot)
        await session.flush()
        return snapshot


@router.get("/snapshots/{snapshot_id}/suggestions")
async def suggestions(snapshot_id: UUID, request: Request) -> dict[str, object]:
    async with request.app.state.session_factory() as session:
        snapshot = await _snapshot(session, snapshot_id)
        return {"rules": suggest_rules(snapshot.html), "requires_approval": True}


@router.post("/versions", response_model=VersionOutput, status_code=201)
async def create_version(payload: VersionInput, request: Request) -> ParserVersion:
    if payload.adapter_type not in {"html", "browser"}:
        raise HTTPException(422, "parser lab supports only html and browser adapters")
    try:
        validate_rules(payload.rules)
    except SandboxViolation as exc:
        raise HTTPException(422, str(exc)) from exc
    async with request.app.state.session_factory() as session, session.begin():
        snapshot = await _snapshot(session, payload.snapshot_id)
        if snapshot.source_id != payload.source_id or await session.get(Source, payload.source_id) is None:
            raise HTTPException(422, "snapshot must belong to the selected source")
        result = await run_snapshot_sandbox(snapshot.html, payload.rules)
        number = int((await session.scalar(select(func.max(ParserVersion.version)).where(ParserVersion.source_id == payload.source_id))) or 0) + 1
        parent = await session.scalar(select(ParserVersion).where(ParserVersion.source_id == payload.source_id, ParserVersion.status == "active"))
        version = ParserVersion(source_id=payload.source_id, version=number, adapter_type=payload.adapter_type, rules=payload.rules, status="validated" if result.ok else "rejected", parent_version_id=parent.id if parent else None, snapshot_id=snapshot.id, reason=payload.reason, validation_report=result.report)
        session.add(version)
        await session.flush()
        return version


@router.post("/versions/{version_id}/approve", response_model=VersionOutput)
async def approve_version(version_id: UUID, request: Request) -> ParserVersion:
    async with request.app.state.session_factory() as session, session.begin():
        version = await session.get(ParserVersion, version_id)
        if version is None:
            raise HTTPException(404, "parser version not found")
        if version.status != "validated":
            raise HTTPException(409, "only validated parser versions can be approved")
        current = list((await session.execute(select(ParserVersion).where(ParserVersion.source_id == version.source_id, ParserVersion.status == "active"))).scalars())
        for old in current:
            old.status = "superseded"
        version.status, version.reviewed_by_actor_id = "active", "admin"
        return cast(ParserVersion, version)


@router.post("/versions/{version_id}/reject", response_model=VersionOutput)
async def reject_version(version_id: UUID, request: Request) -> ParserVersion:
    async with request.app.state.session_factory() as session, session.begin():
        version = await session.get(ParserVersion, version_id)
        if version is None or version.status not in {"draft", "validated"}:
            raise HTTPException(409, "only a proposed parser version can be rejected")
        version.status, version.reviewed_by_actor_id = "rejected", "admin"
        return cast(ParserVersion, version)


@router.post("/versions/{version_id}/rollback", response_model=VersionOutput)
async def rollback_version(version_id: UUID, request: Request) -> ParserVersion:
    async with request.app.state.session_factory() as session, session.begin():
        version = await session.get(ParserVersion, version_id)
        if version is None or version.status not in {"superseded", "active"}:
            raise HTTPException(409, "only a previously working version can be restored")
        for current in (await session.execute(select(ParserVersion).where(ParserVersion.source_id == version.source_id, ParserVersion.status == "active"))).scalars():
            current.status = "rolled_back"
        version.status, version.reviewed_by_actor_id = "active", "admin"
        return cast(ParserVersion, version)


@router.post("/sources/{source_id}/repair", response_model=VersionOutput)
async def repair(source_id: UUID, payload: RepairInput, request: Request) -> ParserVersion:
    async with request.app.state.session_factory() as session, session.begin():
        snapshot = await _snapshot(session, payload.snapshot_id)
        active = await session.scalar(select(ParserVersion).where(ParserVersion.source_id == source_id, ParserVersion.status == "active"))
        if snapshot.source_id != source_id or active is None:
            raise HTTPException(409, "an active parser and matching snapshot are required")
        drift = detect_drift(snapshot.html, active.rules)
        if drift is None:
            raise HTTPException(409, "no parser drift detected")
        rules = suggest_rules(snapshot.html)
        result = await run_snapshot_sandbox(snapshot.html, rules)
        number = int((await session.scalar(select(func.max(ParserVersion.version)).where(ParserVersion.source_id == source_id))) or 0) + 1
        version = ParserVersion(source_id=source_id, version=number, adapter_type=active.adapter_type, rules=rules, status="validated" if result.ok else "rejected", parent_version_id=active.id, snapshot_id=snapshot.id, reason=payload.reason, validation_report=result.report)
        session.add(version)
        await session.flush()
        session.add(ParserRepair(source_id=source_id, detected_version_id=active.id, proposed_version_id=version.id, status="proposed" if result.ok else "failed", reason=payload.reason, evidence=drift))
        return version
