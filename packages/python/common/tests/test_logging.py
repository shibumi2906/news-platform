from __future__ import annotations

import json
from collections.abc import Iterator

import common.logging as logging_module
import pytest
from common.logging import bind_correlation_id, configure_logging, get_correlation_id, get_logger


@pytest.fixture(autouse=True)
def _reset_correlation_id() -> Iterator[None]:
    token = logging_module._correlation_id.set(None)
    yield
    logging_module._correlation_id.reset(token)


def test_bind_and_get_correlation_id() -> None:
    assert get_correlation_id() is None
    bind_correlation_id("11111111-1111-1111-1111-111111111111")
    assert get_correlation_id() == "11111111-1111-1111-1111-111111111111"


def test_configure_logging_emits_single_line_json_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    logger = get_logger("test.module")
    logger.info("something_happened", key="value")

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["event"] == "something_happened"
    assert payload["level"] == "INFO"
    assert payload["key"] == "value"
    assert payload["logger"] == "test.module"
    assert "timestamp" in payload
    assert "correlation_id" not in payload


def test_configure_logging_includes_correlation_id_when_bound(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    bind_correlation_id("22222222-2222-2222-2222-222222222222")
    get_logger("test.module").info("event_with_correlation")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["correlation_id"] == "22222222-2222-2222-2222-222222222222"


def test_configure_logging_filters_below_threshold(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING")
    logger = get_logger("test.module")
    logger.info("should_be_filtered")
    logger.warning("should_appear")

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "should_appear"
    assert payload["level"] == "WARNING"


def test_configure_logging_reads_level_case_insensitively(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("debug")
    get_logger().debug("debug_event")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["event"] == "debug_event"
    assert payload["level"] == "DEBUG"
