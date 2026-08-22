import pytest
import site_api.api.health as health_module
from fastapi import FastAPI
from fastapi.testclient import TestClient
from site_api.main import create_app


def _build_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("INSTANCE_ID", "22222222-2222-2222-2222-222222222222")
    monkeypatch.setenv("INSTANCE_TYPE", "site")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    return create_app()


def test_liveness_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ok_when_db_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)

    async def fake_ping(engine: object) -> bool:
        return True

    monkeypatch.setattr(health_module, "ping", fake_ping)

    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_503_when_db_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)

    async def fake_ping(engine: object) -> bool:
        raise ConnectionError("db down")

    monkeypatch.setattr(health_module, "ping", fake_ping)

    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
