from __future__ import annotations

from common.signing import sign, verify


def test_verify_accepts_matching_signature() -> None:
    signature = sign(
        "s3cret", timestamp="2026-08-06T12:00:00Z", nonce="n-1", idempotency_key="k-1", body=b"{}"
    )

    assert verify(
        "s3cret",
        timestamp="2026-08-06T12:00:00Z",
        nonce="n-1",
        idempotency_key="k-1",
        body=b"{}",
        signature=signature,
    )


def test_verify_rejects_wrong_secret() -> None:
    signature = sign(
        "s3cret", timestamp="2026-08-06T12:00:00Z", nonce="n-1", idempotency_key="k-1", body=b"{}"
    )

    assert not verify(
        "different",
        timestamp="2026-08-06T12:00:00Z",
        nonce="n-1",
        idempotency_key="k-1",
        body=b"{}",
        signature=signature,
    )


def test_verify_rejects_tampered_body() -> None:
    signature = sign(
        "s3cret", timestamp="2026-08-06T12:00:00Z", nonce="n-1", idempotency_key="k-1", body=b"{}"
    )

    assert not verify(
        "s3cret",
        timestamp="2026-08-06T12:00:00Z",
        nonce="n-1",
        idempotency_key="k-1",
        body=b'{"tampered": true}',
        signature=signature,
    )


def test_verify_rejects_replayed_nonce_with_different_timestamp() -> None:
    signature = sign(
        "s3cret", timestamp="2026-08-06T12:00:00Z", nonce="n-1", idempotency_key="k-1", body=b"{}"
    )

    assert not verify(
        "s3cret",
        timestamp="2026-08-06T12:00:01Z",
        nonce="n-1",
        idempotency_key="k-1",
        body=b"{}",
        signature=signature,
    )
