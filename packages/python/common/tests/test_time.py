from datetime import UTC, datetime, timedelta, timezone

from common.time import to_iso8601, utc_now


def test_utc_now_is_timezone_aware_utc() -> None:
    value = utc_now()
    assert value.tzinfo is not None
    assert value.utcoffset() == UTC.utcoffset(None)


def test_to_iso8601_formats_naive_datetime_as_utc_z_suffix() -> None:
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert to_iso8601(naive) == "2026-01-01T12:00:00Z"


def test_to_iso8601_converts_aware_datetime_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    aware = datetime(2026, 1, 1, 14, 0, 0, tzinfo=plus_two)
    assert to_iso8601(aware) == "2026-01-01T12:00:00Z"
