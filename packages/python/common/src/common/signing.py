"""Inter-system request signing (ADR-003, OD-04: HMAC v1).

Every delivery-worker -> Site Ingestion API request is signed over a
canonical string built from the timestamp, nonce, idempotency key and raw
request body, using the shared secret stored on `SiteConnection.hmac_secret`.
The receiving side (site ingestion API) recomputes the signature over the
raw bytes it received and rejects the request on mismatch or on a timestamp
outside the replay window (docs/14 §2, §5).

The key identifier is transported separately from the signed bytes. It selects
an active or overlap verification key; it is not secret.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_VERSION = "v1"

SIGNATURE_VERSION_HEADER = "X-Signature-Version"
SIGNING_KEY_ID_HEADER = "X-Signing-Key-Id"
SIGNATURE_HEADER = "X-Signature"
TIMESTAMP_HEADER = "X-Timestamp"
NONCE_HEADER = "X-Nonce"
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"

#: Identifies which connection's secret to verify against. Stage 1B has no
#: admin UI to negotiate this dynamically, so `SiteConnection.id` (integrator
#: side) and `IntegratorConnection.id` (site side) are provisioned as the
#: same UUID out-of-band when a connection is seeded — this header carries
#: that shared id.
CONNECTION_ID_HEADER = "X-Connection-Id"


def sign(secret: str, *, timestamp: str, nonce: str, idempotency_key: str, body: bytes) -> str:
    base = f"{timestamp}\n{nonce}\n{idempotency_key}\n".encode() + body
    return hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()


def verify(
    secret: str,
    *,
    timestamp: str,
    nonce: str,
    idempotency_key: str,
    body: bytes,
    signature: str,
) -> bool:
    expected = sign(
        secret, timestamp=timestamp, nonce=nonce, idempotency_key=idempotency_key, body=body
    )
    return hmac.compare_digest(expected, signature)
