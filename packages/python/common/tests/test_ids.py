import uuid

from common.ids import new_uuid, new_uuid_str


def test_new_uuid_returns_unique_uuid_objects() -> None:
    first = new_uuid()
    second = new_uuid()
    assert isinstance(first, uuid.UUID)
    assert first != second


def test_new_uuid_str_returns_parseable_uuid_string() -> None:
    value = new_uuid_str()
    assert isinstance(value, str)
    assert uuid.UUID(value)
