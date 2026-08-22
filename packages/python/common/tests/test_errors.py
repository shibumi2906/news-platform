from common.errors import DomainError, ErrorEnvelope


def test_domain_error_carries_message_and_details() -> None:
    error = DomainError("something went wrong", details={"field": "value"})
    assert error.message == "something went wrong"
    assert error.details == {"field": "value"}
    assert error.code == "internal_error"
    assert error.status_code == 500


def test_error_envelope_serializes_expected_shape() -> None:
    envelope = ErrorEnvelope.model_validate(
        {
            "error": {
                "code": "validation_error",
                "message": "invalid input",
                "details": {"field": "title"},
                "correlation_id": "11111111-1111-1111-1111-111111111111",
            }
        }
    )
    dumped = envelope.model_dump()
    assert dumped["error"]["code"] == "validation_error"
    assert dumped["error"]["correlation_id"] == "11111111-1111-1111-1111-111111111111"
