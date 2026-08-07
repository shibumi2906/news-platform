"""S3-compatible object storage abstraction used by the media layer."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote, urlparse

import httpx


class ObjectStorage(Protocol):
    bucket: str

    async def ensure_bucket(self) -> None: ...

    async def put(self, key: str, data: bytes, mime_type: str) -> None: ...

    async def get(self, key: str) -> tuple[bytes, str]: ...

    async def delete(self, key: str) -> None: ...


class S3ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self._client = httpx.AsyncClient(timeout=20)
        self._bucket_ready = False
        self._bucket_lock = asyncio.Lock()

    async def ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        async with self._bucket_lock:
            if self._bucket_ready:
                return
            response = await self._request("HEAD", "")
            if response.status_code == 404:
                response = await self._request("PUT", "")
            response.raise_for_status()
            self._bucket_ready = True

    async def put(self, key: str, data: bytes, mime_type: str) -> None:
        if not self._bucket_ready:
            await self.ensure_bucket()
        response = await self._request("PUT", key, data=data, mime_type=mime_type)
        response.raise_for_status()

    async def get(self, key: str) -> tuple[bytes, str]:
        response = await self._request("GET", key)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "application/octet-stream")

    async def delete(self, key: str) -> None:
        response = await self._request("DELETE", key)
        response.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self, method: str, key: str, *, data: bytes = b"", mime_type: str | None = None
    ) -> httpx.Response:
        timestamp = datetime.now(UTC)
        amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = timestamp.strftime("%Y%m%d")
        parsed = urlparse(self.endpoint_url)
        canonical_uri = f"/{quote(self.bucket, safe='')}"
        if key:
            canonical_uri += f"/{quote(key, safe='/')}"
        payload_hash = hashlib.sha256(data).hexdigest()
        headers = {
            "host": parsed.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if mime_type:
            headers["content-type"] = mime_type
        signed_header_names = ";".join(sorted(headers))
        canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
        canonical_request = "\n".join(
            [method, canonical_uri, "", canonical_headers, signed_header_names, payload_hash]
        )
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signing_key = self._signing_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        headers["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_header_names}, Signature={signature}"
        )
        return await self._client.request(
            method, f"{self.endpoint_url}{canonical_uri}", content=data, headers=headers
        )

    def _signing_key(self, date_stamp: str) -> bytes:
        date_key = hmac.new(
            f"AWS4{self.secret_key}".encode(), date_stamp.encode(), hashlib.sha256
        ).digest()
        region_key = hmac.new(date_key, self.region.encode(), hashlib.sha256).digest()
        service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
        return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


class MemoryObjectStorage:
    """Deterministic storage double; tests still cover real MinIO separately."""

    def __init__(self, bucket: str = "test-media") -> None:
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def ensure_bucket(self) -> None:
        return None

    async def put(self, key: str, data: bytes, mime_type: str) -> None:
        self.objects[key] = (data, mime_type)

    async def get(self, key: str) -> tuple[bytes, str]:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
