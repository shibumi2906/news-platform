"""Dependency-free infrastructure readiness probes."""

from __future__ import annotations

import asyncio
from urllib.parse import unquote, urlparse


async def ping_redis(url: str, *, timeout_seconds: float = 2) -> None:
    parsed = urlparse(url)
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(parsed.hostname, parsed.port or 6379), timeout_seconds
    )
    try:
        if parsed.password:
            await _send(reader, writer, "AUTH", unquote(parsed.password))
        response = await _send(reader, writer, "PING")
        if response != "PONG":
            raise ConnectionError("Redis readiness failed")
    finally:
        writer.close()
        await writer.wait_closed()


async def _send(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *parts: str) -> str:
    payload = f"*{len(parts)}\r\n" + "".join(
        f"${len(part.encode())}\r\n{part}\r\n" for part in parts
    )
    writer.write(payload.encode())
    await writer.drain()
    response = await reader.readline()
    if response.startswith(b"-"):
        raise ConnectionError("Redis returned an error")
    return response[1:-2].decode()
