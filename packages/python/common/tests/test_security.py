from __future__ import annotations

import uuid

import pytest
from common.security import PrincipalSigner, hash_password, verify_password


def test_scrypt_password_hash_and_negative_verification() -> None:
    encoded = hash_password("correct horse battery staple")
    assert "correct horse" not in encoded
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password value", encoded)


def test_principal_signing_rotation_and_tamper_detection() -> None:
    old = "o" * 32
    current = "n" * 32
    signer = PrincipalSigner.from_config(f"v2:{current},v1:{old}")
    token = signer.issue(
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        actor="admin",
        permissions={"users:read"},
        ttl_seconds=60,
        mfa_verified=True,
        auth_method="password",
        now=100,
    )
    principal = signer.verify(token, now=101)
    assert principal is not None and principal.permissions == frozenset({"users:read"})
    assert signer.verify(token + "tampered", now=101) is None
    assert signer.verify(token, now=161) is None


@pytest.mark.parametrize("value", ["", f"v1:{'a' * 32},v1:{'b' * 32}", "missing-secret"])
def test_principal_signing_rejects_ambiguous_or_invalid_keyrings(value: str) -> None:
    with pytest.raises(ValueError):
        PrincipalSigner.from_config(value)
