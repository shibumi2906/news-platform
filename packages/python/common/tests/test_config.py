import pytest
from common.config import BaseAppSettings, InstanceType


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSTANCE_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("INSTANCE_TYPE", "integrator")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")

    settings = BaseAppSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.instance_id == "11111111-1111-1111-1111-111111111111"
    assert settings.instance_type is InstanceType.INTEGRATOR
    assert settings.app_env == "development"
    assert settings.timezone == "UTC"


def test_settings_reject_unknown_instance_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSTANCE_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("INSTANCE_TYPE", "not-a-real-type")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")

    with pytest.raises(ValueError):
        BaseAppSettings(_env_file=None)  # type: ignore[call-arg]


def test_production_settings_fail_closed_and_accept_explicit_secure_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INSTANCE_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("INSTANCE_TYPE", "site")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db.internal:5432/site")
    monkeypatch.setenv("REDIS_URL", "redis://:strong-password@redis.internal:6379/0")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.internal")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://news.example")
    monkeypatch.setenv("ADMIN_SESSION_KEYS", f"v1:{'s' * 32}")
    settings = BaseAppSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.app_env == "production"
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://news.example")
    with pytest.raises(ValueError, match="HTTPS"):
        BaseAppSettings(_env_file=None)  # type: ignore[call-arg]
