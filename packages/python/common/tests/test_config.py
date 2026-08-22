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
