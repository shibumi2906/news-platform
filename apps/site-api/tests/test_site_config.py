from __future__ import annotations

import pytest
from site_api.config import Settings


def _production_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "INSTANCE_ID": "11111111-1111-1111-1111-111111111111",
        "INSTANCE_TYPE": "site",
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@db.internal:5432/site",
        "REDIS_URL": "redis://:strong-password@redis.internal:6379/0",
        "ALLOWED_HOSTS": "site-api",
        "ALLOWED_ORIGINS": "https://news.example",
        "ADMIN_API_TOKEN": "a" * 32,
        "ADMIN_SESSION_KEYS": f"v1:{'s' * 32}",
        "S3_ACCESS_KEY": "production-access",
        "S3_SECRET_KEY": "production-secret",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_production_bootstrap_credentials_can_be_removed_after_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_environment(monkeypatch)
    monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", "")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert not settings.admin_bootstrap_username


def test_production_bootstrap_credentials_must_be_a_complete_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_environment(monkeypatch)
    monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "")
    with pytest.raises(ValueError, match="set together"):
        Settings(_env_file=None)  # type: ignore[call-arg]
