from __future__ import annotations

import pytest
from site_domain.distribution_capabilities import capabilities_for


@pytest.mark.parametrize("kind", ["telegram", "facebook", "instagram", "tiktok", "x", "youtube"])
def test_real_provider_has_declared_capabilities(kind: str) -> None:
    assert capabilities_for(kind).text_limit > 0


def test_x_does_not_schedule_media_without_an_upload_authorization_adapter() -> None:
    assert "image" not in capabilities_for("x").content_types
    assert "video" not in capabilities_for("x").content_types


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported distribution channel kind"):
        capabilities_for("not-a-provider")
