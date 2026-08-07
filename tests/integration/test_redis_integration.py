"""Real Redis connectivity and idempotency primitive integration test."""

from __future__ import annotations

import asyncio
import os
import uuid
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("REDIS_TEST_URL"), reason="requires REDIS_TEST_URL")


async def _command(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *args: str) -> str:
    payload = f"*{len(args)}\r\n" + "".join(f"${len(arg.encode())}\r\n{arg}\r\n" for arg in args)
    writer.write(payload.encode())
    await writer.drain()
    response = await reader.readline()
    if response.startswith(b"$"):
        size = int(response[1:-2])
        if size == -1:
            return ""
        value = await reader.readexactly(size)
        await reader.readexactly(2)
        return value.decode()
    return response[1:-2].decode()


async def _run() -> None:
    parsed = urlparse(os.environ["REDIS_TEST_URL"])
    reader, writer = await asyncio.open_connection(parsed.hostname, parsed.port or 6379)
    try:
        if parsed.password:
            assert await _command(reader, writer, "AUTH", parsed.password) == "OK"
        assert await _command(reader, writer, "PING") == "PONG"
        key = f"integration:idempotency:{uuid.uuid4().hex}"
        assert await _command(reader, writer, "SET", key, "claimed", "NX", "EX", "30") == "OK"
        assert await _command(reader, writer, "SET", key, "duplicate", "NX", "EX", "30") == ""
        assert await _command(reader, writer, "GET", key) == "claimed"
        await _command(reader, writer, "DEL", key)
    finally:
        writer.close()
        await writer.wait_closed()


def test_real_redis_ping_and_idempotent_claim() -> None:
    asyncio.run(_run())
