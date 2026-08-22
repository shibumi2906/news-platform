from __future__ import annotations

from common.hashing import sha256_hex


def test_sha256_hex_is_deterministic() -> None:
    assert sha256_hex("https://example.com/a") == sha256_hex("https://example.com/a")


def test_sha256_hex_differs_for_different_input() -> None:
    assert sha256_hex("https://example.com/a") != sha256_hex("https://example.com/b")


def test_sha256_hex_is_lowercase_hex_64_chars() -> None:
    digest = sha256_hex("https://example.com/a")
    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)  # raises ValueError if not valid hex
