"""Password hashing, rotatable signed principals, and IdP/MFA contracts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Protocol


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    salt = salt or os.urandom(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_encode(salt)}${_encode(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=_decode(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(actual, _decode(expected))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class Principal:
    session_id: uuid.UUID
    user_id: uuid.UUID
    actor: str
    permissions: frozenset[str]
    expires_at: int
    mfa_verified: bool
    auth_method: str


class PrincipalSigner:
    """HMAC signer supporting current+previous keys during rotation."""

    def __init__(self, keys: dict[str, str], *, current_key_id: str) -> None:
        if current_key_id not in keys or not keys[current_key_id]:
            raise ValueError("current session signing key is unavailable")
        self.keys = keys
        self.current_key_id = current_key_id

    @classmethod
    def from_config(cls, value: str) -> PrincipalSigner:
        keys: dict[str, str] = {}
        for item in value.split(","):
            key_id, separator, secret = item.partition(":")
            if not separator or not key_id or len(secret) < 32:
                raise ValueError("session signing keys must be kid:secret with 32+ char secrets")
            keys[key_id] = secret
        return cls(keys, current_key_id=next(iter(keys)))

    def issue(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        actor: str,
        permissions: set[str],
        ttl_seconds: int,
        mfa_verified: bool,
        auth_method: str,
        now: int | None = None,
    ) -> str:
        issued_at = now or int(time.time())
        payload = {
            "sid": str(session_id),
            "sub": str(user_id),
            "actor": actor,
            "permissions": sorted(permissions),
            "iat": issued_at,
            "exp": issued_at + ttl_seconds,
            "mfa": mfa_verified,
            "amr": auth_method,
            "kid": self.current_key_id,
        }
        encoded = _encode(json.dumps(payload, separators=(",", ":")).encode())
        signature = self._sign(encoded, self.current_key_id)
        return f"{encoded}.{signature}"

    def verify(self, token: str, *, now: int | None = None) -> Principal | None:
        try:
            encoded, signature = token.split(".")
            payload = json.loads(_decode(encoded))
            key_id = payload["kid"]
            if key_id not in self.keys or not secrets.compare_digest(
                signature, self._sign(encoded, key_id)
            ):
                return None
            if int(payload["exp"]) <= (now or int(time.time())):
                return None
            return Principal(
                session_id=uuid.UUID(payload["sid"]),
                user_id=uuid.UUID(payload["sub"]),
                actor=str(payload["actor"]),
                permissions=frozenset(str(item) for item in payload["permissions"]),
                expires_at=int(payload["exp"]),
                mfa_verified=bool(payload["mfa"]),
                auth_method=str(payload["amr"]),
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _sign(self, payload: str, key_id: str) -> str:
        return _encode(
            hmac.new(self.keys[key_id].encode(), payload.encode(), hashlib.sha256).digest()
        )


class IdentityProvider(Protocol):
    name: str

    async def authenticate(self, identifier: str, credential: str) -> str | None: ...


class OIDCProvider(Protocol):
    issuer: str

    async def authorization_url(self, *, state: str, nonce: str) -> str: ...

    async def exchange_code(self, code: str, *, nonce: str) -> dict[str, object]: ...


class MFAVerifier(Protocol):
    async def verify(self, user_id: uuid.UUID, assertion: str) -> bool: ...


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
